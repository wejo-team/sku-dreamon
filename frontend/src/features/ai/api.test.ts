// 실제 POST SSE의 청크·수명주기·CSRF와 제어 요청 계약을 검증합니다.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, resetCsrfToken } from '@/lib/api';
import {
  startChat,
  retryAi,
  cancelAi,
  validateAiResult,
  startApplicantReview,
  startApplicantRecommendations,
  retryApplicants,
} from './api';
import { AiStreamError } from './stream';
import { ChatStart, type AiEvent, type ChatResult } from './contract';

const id = '00000000-0000-4000-8000-000000000001';
const body = {
  requestId: id,
  conversationId: '00000000-0000-4000-8000-000000000002',
  clientMessageId: '00000000-0000-4000-8000-000000000003',
  content: '팀 찾아줘',
  history: [],
  previousResults: [],
};
const result: ChatResult = {
  kind: 'chat',
  answer: '한글 😀 답변',
  cards: [],
  generatedAt: '2026-10-28T00:00:00Z',
  referencesChanged: false,
};
const state = {
  id,
  purpose: 'chat',
  conversationId: body.conversationId,
  teamId: null,
  applicationId: null,
  attempt: 1,
  status: 'canceled',
  failure: null,
  expiresAt: '2026-10-29T00:00:00Z',
};
const frame = (
  event: string,
  sequence: number,
  payload: object = {},
  attempt = 1,
) =>
  `event: ${event}\ndata: ${JSON.stringify({ requestId: id, attempt, sequence, ...payload })}\n\n`;
const complete = (attempt = 1) =>
  frame('started', 1, { purpose: 'chat' }, attempt) +
  frame('progress', 2, { stage: 'writing' }, attempt) +
  frame('answer.delta', 3, { text: result.answer }, attempt) +
  frame('result', 4, { result }, attempt) +
  frame('done', 5, { status: 'empty' }, attempt);
function streamed(text: string, bytewise = false) {
  const bytes = new TextEncoder().encode(text);
  return new Response(
    new ReadableStream<Uint8Array>({
      start(c) {
        if (bytewise)
          for (const byte of bytes) c.enqueue(new Uint8Array([byte]));
        else c.enqueue(bytes);
        c.close();
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } },
  );
}
function mock(response: Response) {
  const fetch = vi
    .fn<typeof globalThis.fetch>()
    .mockResolvedValueOnce(Response.json({ data: { csrfToken: 'test-csrf' } }))
    .mockResolvedValueOnce(response);
  vi.stubGlobal('fetch', fetch);
  return fetch;
}
beforeEach(() => resetCsrfToken());
describe('POST AI SSE', () => {
  it('다중 이벤트·heartbeat·CRLF·UTF8 분할을 처리하고 쿠키와 CSRF를 전송한다', async () => {
    const fetch = mock(
      streamed((': heartbeat\n\n' + complete()).replaceAll('\n', '\r\n'), true),
    );
    const events: AiEvent[] = [];
    await startChat(body, (e) => events.push(e));
    expect(events.map((e) => e.event)).toEqual([
      'started',
      'progress',
      'answer.delta',
      'result',
      'done',
    ]);
    expect(events[2]).toMatchObject({ text: '한글 😀 답변' });
    const [url, init] = fetch.mock.calls[1]!;
    expect(url).toBe('/api/v1/ai/chat/stream');
    expect(init?.credentials).toBe('include');
    expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe('test-csrf');
    expect(new Headers(init?.headers).get('Accept')).toBe('text/event-stream');
    expect(JSON.parse(String(init?.body))).toEqual(body);
  });
  it.each(['\n', '\r', '\r\n'])(
    'SSE 줄 구분 %j 및 여러 data 줄을 처리한다',
    async (newline) => {
      mock(
        streamed(
          complete()
            .replaceAll('data: {', 'data: {\ndata: ')
            .replaceAll('\n', newline),
          true,
        ),
      );
      await expect(startChat(body, () => {})).resolves.toBeUndefined();
    },
  );
  it('done 이전 EOF는 전체 result를 받았어도 성공이 아니다', async () => {
    mock(
      streamed(complete().replace(frame('done', 5, { status: 'empty' }), '')),
    );
    await expect(startChat(body, () => {})).rejects.toMatchObject({
      kind: 'interrupted',
    });
  });
  it.each([
    [
      '다른 요청',
      complete().replaceAll(id, '00000000-0000-4000-8000-000000000099'),
    ],
    ['이전 시도', complete(2)],
    ['중복 sequence', complete().replace('"sequence":3', '"sequence":2')],
    [
      '잘못된 목적',
      complete().replace('"purpose":"chat"', '"purpose":"applicant_review"'),
    ],
    [
      'result 없는 done',
      frame('started', 1, { purpose: 'chat' }) +
        frame('done', 2, { status: 'empty' }),
    ],
    [
      '필드 위반',
      complete().replace('"purpose":"chat"', '"purpose":"chat","text":"leak"'),
    ],
    [
      '잘못된 JSON',
      frame('started', 1, { purpose: 'chat' }) +
        'event: result\ndata: broken\n\n',
    ],
  ])('%s 프로토콜 위반을 거부한다', async (_name, text) => {
    mock(streamed(text));
    await expect(startChat(body, () => {})).rejects.toBeInstanceOf(
      AiStreamError,
    );
  });
  it.each(['error', 'canceled', 'invalidated'])(
    '%s 종료를 성공 done으로 바꾸지 않는다',
    async (event) => {
      const payload =
        event === 'error'
          ? {
              failure: {
                code: 'temporary_failure',
                message: '다시 시도해 주세요',
                retryable: true,
              },
            }
          : event === 'invalidated'
            ? { reason: 'context_changed' }
            : {};
      mock(
        streamed(
          frame('started', 1, { purpose: 'chat' }) + frame(event, 2, payload),
        ),
      );
      const seen: AiEvent[] = [];
      await startChat(body, (e) => seen.push(e));
      expect(seen.at(-1)?.event).toBe(event);
      expect(seen.some((e) => e.event === 'done')).toBe(false);
    },
  );
  it('스트림 시작 전 503 JSON 오류를 보존한다', async () => {
    mock(
      Response.json(
        {
          error: { code: 'AI_NOT_CONFIGURED', message: '설정 필요' },
          requestId: 'trace',
        },
        { status: 503 },
      ),
    );
    await expect(startChat(body, () => {})).rejects.toMatchObject({
      status: 503,
      code: 'AI_NOT_CONFIGURED',
    });
  });
  it('청크 안의 이벤트 처리 중 취소하면 나머지 이벤트를 전달하지 않는다', async () => {
    mock(streamed(complete()));
    const controller = new AbortController();
    const seen: AiEvent[] = [];
    await expect(
      startChat(
        body,
        (event) => {
          seen.push(event);
          controller.abort();
        },
        controller.signal,
      ),
    ).rejects.toMatchObject({ name: 'AbortError' });
    expect(seen.map((event) => event.event)).toEqual(['started']);
  });
  it('이벤트 스트림과 비슷한 잘못된 MIME을 거부한다', async () => {
    mock(
      new Response(complete(), {
        headers: { 'Content-Type': 'application/not-text/event-stream' },
      }),
    );
    await expect(startChat(body, () => {})).rejects.toMatchObject({
      kind: 'protocol',
    });
  });
  it('JSON 성공을 SSE로 오인하지 않는다', async () => {
    mock(Response.json({ data: {} }));
    await expect(startChat(body, () => {})).rejects.toMatchObject({
      kind: 'protocol',
    });
  });
  it('재시도는 원래 입력과 expectedAttempt를 보내고 새 시도만 수락한다', async () => {
    const fetch = mock(streamed(complete(2)));
    await retryAi(id, { expectedAttempt: 1, input: body }, 'chat', () => {});
    expect(fetch.mock.calls[1]![0]).toBe(
      `/api/v1/ai/requests/${id}/retries/stream`,
    );
    expect(JSON.parse(String(fetch.mock.calls[1]![1]?.body))).toEqual({
      expectedAttempt: 1,
      input: body,
    });
  });
  it('중단은 현재 expectedAttempt로 PUT한다', async () => {
    const fetch = mock(Response.json({ data: state }));
    await expect(cancelAi(id, 1)).resolves.toEqual(state);
    expect(fetch.mock.calls[1]![1]?.method).toBe('PUT');
    expect(JSON.parse(String(fetch.mock.calls[1]![1]?.body))).toEqual({
      expectedAttempt: 1,
    });
  });
  it('validation은 원본 result를 보내고 무효를 보존한다', async () => {
    const fetch = mock(Response.json({ data: { valid: false, result: null } }));
    await expect(validateAiResult(id, 1, result)).resolves.toEqual({
      valid: false,
      result: null,
    });
    expect(JSON.parse(String(fetch.mock.calls[1]![1]?.body))).toEqual({
      attempt: 1,
      result,
    });
  });
  it('403은 자동 재전송하지 않고 CSRF만 폐기한다', async () => {
    const fetch = mock(
      Response.json(
        { error: { code: 'FORBIDDEN', message: '거부' }, requestId: 'trace' },
        { status: 403 },
      ),
    );
    await expect(startChat(body, () => {})).rejects.toBeInstanceOf(ApiError);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('NFC·코드포인트 한도·고립 surrogate를 검증한다', () => {
    expect(
      ChatStart.parse({ ...body, content: '😀'.repeat(1000) }).content,
    ).toHaveLength(2000);
    expect(() =>
      ChatStart.parse({ ...body, content: 'a'.repeat(1001) }),
    ).toThrow();
    expect(() => ChatStart.parse({ ...body, content: '\uD800' })).toThrow();
    expect(() =>
      ChatStart.parse({ ...body, history: Array(13).fill('a'.repeat(1000)) }),
    ).toThrow();
  });
});

describe('지원자 JSON 평가', () => {
  const review = {
    schemaVersion: 3,
    kind: 'applicant_review',
    applicationId: id,
    summary: '검토를 완료했어요.',
    assessment: {
      criteria: ['role', 'skills', 'experience', 'availability'].map((key) => ({
        key,
        score: null,
        informationStatus: 'insufficient',
        summary: '자료가 필요해요.',
        evidence: [],
      })),
      questions: [],
    },
    evidence: [],
    profileVersions: [{ accountId: id, usedVersion: '1', currentVersion: '1' }],
    isStale: false,
    isSelectionCandidate: true,
    generatedAt: '2026-10-28T00:00:00Z',
  };
  const completion = {
    requestId: id,
    attempt: 1,
    status: 'succeeded',
    result: review,
  };
  it('완료 JSON을 쿠키·CSRF·AbortSignal을 유지하며 받는다', async () => {
    const fetch = mock(Response.json({ data: completion }));
    const signal = new AbortController().signal;
    await expect(
      startApplicantReview(id, { requestId: id }, signal),
    ).resolves.toEqual(completion);
    const [url, init] = fetch.mock.calls[1]!;
    expect(url).toBe(`/api/v1/applications/${id}/ai-reviews`);
    expect(init?.credentials).toBe('include');
    expect(init?.signal).toBe(signal);
    expect(new Headers(init?.headers).get('Accept')).toBe('application/json');
    expect(new Headers(init?.headers).get('X-CSRF-Token')).toBe('test-csrf');
  });
  it('추천의 빈 완료 결과도 JSON으로 받는다', async () => {
    const empty = {
      ...completion,
      status: 'empty',
      result: {
        schemaVersion: 3,
        kind: 'applicant_recommendation',
        summary: '지원자가 없어요.',
        candidates: [],
        isStale: false,
        generatedAt: review.generatedAt,
      },
    };
    const fetch = mock(Response.json({ data: empty }));
    await expect(
      startApplicantRecommendations(id, { requestId: id }),
    ).resolves.toEqual(empty);
    expect(fetch.mock.calls[1]![0]).toBe(
      `/api/v1/teams/${id}/applicant-recommendations`,
    );
  });
  it('지원자 재시도는 JSON 경로와 원래 요청·이전 attempt를 사용한다', async () => {
    const fetch = mock(Response.json({ data: { ...completion, attempt: 2 } }));
    await retryApplicants(
      id,
      { expectedAttempt: 1, input: { requestId: id } },
      'applicant_review',
    );
    expect(fetch.mock.calls[1]![0]).toBe(`/api/v1/ai/requests/${id}/retries`);
    expect(JSON.parse(String(fetch.mock.calls[1]![1]?.body))).toEqual({
      expectedAttempt: 1,
      input: { requestId: id },
    });
  });
  it.each([
    { ...completion, requestId: body.conversationId },
    { ...completion, attempt: 2 },
    {
      ...completion,
      result: { ...review, applicationId: body.conversationId },
    },
    { ...completion, result: { ...review, schemaVersion: 2 } },
    { ...completion, result },
    { ...completion, result: null },
    { ...completion, status: 'canceled' },
  ])('다른 요청·대상·버전 또는 불완전한 결과를 거부한다', async (invalid) => {
    mock(Response.json({ data: invalid }));
    await expect(startApplicantReview(id, { requestId: id })).rejects.toThrow();
  });
  it.each(['canceled', 'invalidated'])(
    '%s 결과를 성공으로 바꾸지 않는다',
    async (status) => {
      const terminated = { ...completion, status, result: null };
      mock(Response.json({ data: terminated }));
      await expect(
        startApplicantReview(id, { requestId: id }),
      ).resolves.toEqual(terminated);
    },
  );
});
