import { act, fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, Route, Routes } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { AiChatPage } from './AiChatPage';
import {
  ChatStart,
  type AiRequestView,
  type ChatResult,
  type ResultValidation,
} from './contract';
import { useLogin, useLogout } from '@/features/auth/queries';
import { demoId, demoPassword } from '@/features/demo/auth-policy';
import { demoIds, renderWithApi, settled } from '@/test/render';

function Navigation() {
  const login = useLogin();
  const logout = useLogout();
  return (
    <nav>
      <Link to="/ai">AI로 돌아가기</Link>
      <Link to="/elsewhere">다른 화면</Link>
      <button onClick={() => logout.mutate()}>테스트 로그아웃</button>
      <button
        onClick={() =>
          login.mutate({ loginId: demoId, password: demoPassword })
        }
      >
        같은 계정 재로그인
      </button>
    </nav>
  );
}
const result: ChatResult = {
  kind: 'chat',
  answer: '현재 공개 자료로 확인한 답변입니다.',
  cards: [
    {
      kind: 'person',
      resourceId: demoIds.accounts.me,
      title: '공개 추천 대상',
      reason: '등록한 관심 분야가 요청과 관련돼요.',
      fieldCodes: ['it'],
      roleCodes: ['development'],
      isDemo: true,
    },
  ],
  generatedAt: '2026-10-28T00:00:00Z',
  referencesChanged: false,
};
const failure = {
  code: 'temporary_failure' as const,
  message: '잠시 답변을 만들지 못했어요.',
  retryable: true,
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
type Stream = {
  input: ChatStart;
  attempt: number;
  emit: (event: string, payload?: object) => void;
  end: () => void;
  closed: () => boolean;
};
async function setup() {
  const { client } = renderWithApi(
    <>
      <Navigation />
      <Routes>
        <Route path="/ai" element={<AiChatPage />} />
        <Route path="/elsewhere" element={<p>다른 화면 내용</p>} />
        <Route path="/people/:id" element={<p>추천 상세 화면</p>} />
      </Routes>
    </>,
    { path: '/ai', signedIn: true },
  );
  await settled(client);
  const delegate = fetch;
  const streams: Stream[] = [];
  const validations: { attempt: number; result: ChatResult }[] = [];
  const cancellations: { requestId: string; expectedAttempt: number }[] = [];
  const retryBodies: unknown[] = [];
  const views = new Map<string, AiRequestView>();
  let validate = async (body: {
    attempt: number;
    result: ChatResult;
  }): Promise<Response> =>
    Response.json({ data: { valid: true, result: body.result } });
  let startFailure: Response | null = null;
  let statusResponse: ((id: string) => Promise<Response>) | null = null;
  vi.stubGlobal('fetch', async (input: string, init: RequestInit = {}) => {
    const path = new URL(input, 'http://test.invalid').pathname.replace(
      /^\/api\/v1/,
      '',
    );
    const body: unknown =
      typeof init.body === 'string' ? JSON.parse(init.body) : undefined;
    if (path.endsWith('/validation')) {
      const parsed = body as { attempt: number; result: ChatResult };
      validations.push(parsed);
      return validate(parsed);
    }
    if (path.endsWith('/cancellation')) {
      const requestId = path.split('/')[3]!;
      const { expectedAttempt } = body as { expectedAttempt: number };
      cancellations.push({ requestId, expectedAttempt });
      const view = { ...views.get(requestId)!, status: 'canceled' as const };
      views.set(requestId, view);
      return Response.json({ data: view });
    }
    if (path === '/ai/chat/stream' || path.endsWith('/retries/stream')) {
      if (startFailure) return startFailure;
      const retry = path.endsWith('/retries/stream');
      if (retry) retryBodies.push(body);
      const parsed = ChatStart.parse(
        retry ? (body as { input: ChatStart }).input : body,
      );
      const attempt = retry
        ? (body as { expectedAttempt: number }).expectedAttempt + 1
        : 1;
      let writer!: ReadableStreamDefaultController<Uint8Array>;
      let closed = false;
      let sequence = 0;
      const stream = new ReadableStream<Uint8Array>({
        start(controller) {
          writer = controller;
        },
        cancel() {
          closed = true;
        },
      });
      const view: AiRequestView = {
        id: parsed.requestId,
        purpose: 'chat',
        conversationId: parsed.conversationId,
        teamId: null,
        applicationId: null,
        attempt,
        status: 'pending',
        failure: null,
        expiresAt: '2026-10-29T00:00:00Z',
      };
      views.set(parsed.requestId, view);
      const control: Stream = {
        input: parsed,
        attempt,
        emit(event, payload = {}) {
          if (closed) return;
          if (event === 'error')
            views.set(parsed.requestId, { ...view, status: 'failed', failure });
          if (event === 'done')
            views.set(parsed.requestId, { ...view, status: 'succeeded' });
          writer.enqueue(
            new TextEncoder().encode(
              `event: ${event}\ndata: ${JSON.stringify({ requestId: parsed.requestId, attempt, sequence: ++sequence, ...payload })}\n\n`,
            ),
          );
        },
        end() {
          if (!closed) {
            writer.close();
            closed = true;
          }
        },
        closed: () => closed,
      };
      streams.push(control);
      control.emit('started', { purpose: 'chat' });
      return new Response(stream, {
        headers: { 'Content-Type': 'text/event-stream' },
      });
    }
    if (path.startsWith('/ai/requests/')) {
      if (statusResponse) return statusResponse(path.split('/')[3]!);
      const view = views.get(path.split('/')[3]!);
      return view
        ? Response.json({ data: view })
        : Response.json(
            {
              error: { code: 'RESOURCE_NOT_FOUND', message: '없음' },
              requestId: crypto.randomUUID(),
            },
            { status: 404 },
          );
    }
    return delegate(input, init);
  });
  const user = userEvent.setup();
  const send = async (text = '현재 공개된 사람 찾아줘') => {
    const before = streams.length;
    await user.type(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
      text,
    );
    await user.click(screen.getByRole('button', { name: '메시지 보내기' }));
    await waitFor(() => expect(streams).toHaveLength(before + 1));
    return streams.at(-1)!;
  };
  const finish = async (
    stream: Stream,
    answer = result,
    status: 'succeeded' | 'empty' = 'succeeded',
  ) => {
    await act(async () => {
      stream.emit('answer.delta', { text: answer.answer });
      stream.emit('result', { result: answer });
      stream.emit('done', { status });
    });
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: '응답 중지' }),
      ).not.toBeInTheDocument(),
    );
  };
  return {
    client,
    user,
    streams,
    validations,
    retryBodies,
    cancellations,
    views,
    send,
    finish,
    validation: (handler: typeof validate) => {
      validate = handler;
    },
    statusResponse: (handler: (id: string) => Promise<Response>) => {
      statusResponse = handler;
    },
    startError: (response: Response) => {
      startFailure = response;
    },
  };
}

describe('actual AI chat UI and SSE API', () => {
  it('streams partial text, withholds cards and copying until done and validation, then sends only user context', async () => {
    const app = await setup();
    const stream = await app.send('  첫 질문  ');
    expect(stream.input.content).toBe('첫 질문');
    expect(stream.input.history).toEqual([]);
    expect(stream.input.previousResults).toEqual([]);
    await act(async () => {
      stream.emit('answer.delta', { text: '작성 중인 일부 답변' });
    });
    expect(screen.getByText('작성 중인 일부 답변')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '답변 복사' }),
    ).not.toBeInTheDocument();
    const waiting = deferred<Response>();
    app.validation(() => waiting.promise);
    await act(async () => {
      stream.emit('result', { result });
      stream.emit('done', { status: 'succeeded' });
    });
    await waitFor(() => expect(app.validations).toHaveLength(1));
    expect(screen.queryByText(result.answer)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /공개 추천 대상/ }),
    ).not.toBeInTheDocument();
    await act(async () =>
      waiting.resolve(Response.json({ data: { valid: true, result } })),
    );
    expect(await screen.findByText(result.answer)).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /공개 추천 대상/ }),
    ).toHaveAttribute('href', `/people/${demoIds.accounts.me}?from=%2Fai`);
    const second = await app.send('분야를 바꿔줘');
    expect(second.input.conversationId).toBe(stream.input.conversationId);
    expect(second.input.history).toEqual(['첫 질문']);
    expect(second.input.previousResults).toEqual([
      { requestId: stream.input.requestId, attempt: 1 },
    ]);
    expect(JSON.stringify(second.input)).not.toContain(result.answer);
  });

  it('retries the exact original input and preserves the unsent draft', async () => {
    const app = await setup();
    const first = await app.send();
    await act(async () => {
      first.emit('error', { failure });
    });
    await app.user.type(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
      '아직 보내지 않은 초안',
    );
    await app.user.click(
      await screen.findByRole('button', { name: '다시 시도' }),
    );
    await waitFor(() => expect(app.streams).toHaveLength(2));
    expect(app.retryBodies).toEqual([
      { expectedAttempt: 1, input: first.input },
    ]);
    expect(app.streams[1]!.attempt).toBe(2);
    expect(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
    ).toHaveValue('아직 보내지 않은 초안');
    await app.finish(app.streams[1]!);
    expect(app.validations[0]!.attempt).toBe(2);
  });

  it('cancels the server attempt and never accepts late text; new conversation gets new IDs', async () => {
    const app = await setup();
    const first = await app.send();
    await act(async () =>
      first.emit('answer.delta', { text: '중단할 부분 답변' }),
    );
    await app.user.click(screen.getByRole('button', { name: '응답 중지' }));
    await waitFor(() =>
      expect(app.cancellations).toEqual([
        { requestId: first.input.requestId, expectedAttempt: 1 },
      ]),
    );
    expect(screen.queryByText('중단할 부분 답변')).not.toBeInTheDocument();
    expect(first.closed()).toBe(true);
    await app.user.click(screen.getByRole('button', { name: '새 대화' }));
    const second = await app.send();
    expect(second.input.conversationId).not.toBe(first.input.conversationId);
    expect(second.input.requestId).not.toBe(first.input.requestId);
    expect(second.input.history).toEqual([]);
    await app.user.click(screen.getByRole('button', { name: '새 대화' }));
    await waitFor(() => expect(app.cancellations).toHaveLength(2));
    expect(screen.getByText('어떤 도전을 찾고 있나요?')).toBeInTheDocument();
  });

  it('discards partial answers on invalidated events and shows no copy action', async () => {
    const app = await setup();
    const stream = await app.send();
    await act(async () =>
      stream.emit('answer.delta', { text: '권한이 사라질 민감한 답변' }),
    );
    await act(async () =>
      stream.emit('invalidated', { reason: 'context_changed' }),
    );
    expect(
      await screen.findByText(/정보나 접근 권한이 바뀌어/),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('권한이 사라질 민감한 답변'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '답변 복사' }),
    ).not.toBeInTheDocument();
  });

  it('does not restore a result after EOF without done even when status reports success', async () => {
    const app = await setup();
    const stream = await app.send();
    const view = app.views.get(stream.input.requestId)!;
    app.views.set(stream.input.requestId, { ...view, status: 'succeeded' });
    await act(async () => {
      stream.emit('answer.delta', { text: '끊긴 답변' });
      stream.emit('result', { result });
      stream.end();
    });
    expect(
      await screen.findByText(/답변을 끝까지 받지 못했어요/),
    ).toBeInTheDocument();
    expect(screen.queryByText('끊긴 답변')).not.toBeInTheDocument();
    expect(screen.queryByText(result.answer)).not.toBeInTheDocument();
    expect(app.validations).toHaveLength(0);
    await app.user.click(
      screen.getByRole('button', { name: '같은 내용으로 다시 요청' }),
    );
    await waitFor(() => expect(app.streams).toHaveLength(2));
    expect(app.streams[1]!.input.requestId).not.toBe(stream.input.requestId);
    expect(app.streams[1]!.input.clientMessageId).not.toBe(
      stream.input.clientMessageId,
    );
  });

  it('uses the first result on every validation and copies only after fresh validation', async () => {
    const app = await setup();
    const stream = await app.send();
    app.validation(async (body) =>
      Response.json({
        data: {
          valid: true,
          result: { ...body.result, referencesChanged: true },
        },
      }),
    );
    await app.finish(stream);
    const copy = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
    await app.user.click(screen.getByRole('button', { name: '답변 복사' }));
    await waitFor(() => expect(copy).toHaveBeenCalledOnce());
    expect(app.validations).toHaveLength(2);
    expect(
      app.validations.every((body) => body.result.referencesChanged === false),
    ).toBe(true);
    expect(copy).toHaveBeenCalledWith(
      `${result.answer}\n\n${result.cards[0]!.title}\n${result.cards[0]!.reason}`,
    );
    app.validation(async () =>
      Response.json({
        data: { valid: false, result: null } satisfies ResultValidation,
      }),
    );
    await app.user.click(screen.getByRole('button', { name: '답변 복사' }));
    expect(
      await screen.findByText(/정보나 접근 권한이 바뀌어/),
    ).toBeInTheDocument();
    expect(screen.queryByText(result.answer)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /공개 추천 대상/ }),
    ).not.toBeInTheDocument();
    expect(copy).toHaveBeenCalledOnce();
  });

  it('keeps tab conversation and draft through detail navigation, revalidates return and hides failed focus validation', async () => {
    const app = await setup();
    await app.finish(await app.send());
    await app.user.type(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
      '보관할 초안',
    );
    await app.user.click(screen.getByRole('link', { name: /공개 추천 대상/ }));
    expect(screen.getByText('추천 상세 화면')).toBeInTheDocument();
    const waiting = deferred<Response>();
    app.validation(() => waiting.promise);
    await app.user.click(screen.getByRole('link', { name: 'AI로 돌아가기' }));
    expect(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
    ).toHaveValue('보관할 초안');
    expect(screen.queryByText(result.answer)).not.toBeInTheDocument();
    await act(async () =>
      waiting.resolve(Response.json({ data: { valid: true, result } })),
    );
    expect(await screen.findByText(result.answer)).toBeInTheDocument();
    app.validation(async () => new Response(null, { status: 503 }));
    fireEvent.focus(window);
    expect(
      await screen.findByText(/현재 정보를 확인하지 못해/),
    ).toBeInTheDocument();
    expect(screen.queryByText(result.answer)).not.toBeInTheDocument();
    app.validation(async () =>
      Response.json({ data: { valid: true, result } }),
    );
    await app.user.click(screen.getByRole('button', { name: '다시 확인' }));
    expect(await screen.findByText(result.answer)).toBeInTheDocument();
  });

  it('clears same-account re-login memory and ignores an older validation response', async () => {
    const app = await setup();
    await app.finish(await app.send());
    const waiting = deferred<Response>();
    app.validation(() => waiting.promise);
    fireEvent.focus(window);
    await waitFor(() => expect(app.validations).toHaveLength(2));
    await app.user.click(
      screen.getByRole('button', { name: '같은 계정 재로그인' }),
    );
    await waitFor(() =>
      expect(screen.getByText('어떤 도전을 찾고 있나요?')).toBeInTheDocument(),
    );
    await act(async () =>
      waiting.resolve(Response.json({ data: { valid: true, result } })),
    );
    expect(screen.queryByText(result.answer)).not.toBeInTheDocument();
    expect(
      screen.queryByText('현재 공개된 사람 찾아줘'),
    ).not.toBeInTheDocument();
  });

  it('expires a 401 session and removes the whole conversation without a retry loop', async () => {
    const app = await setup();
    await app.finish(await app.send());
    app.validation(async () =>
      Response.json(
        {
          error: { code: 'UNAUTHENTICATED', message: '로그인이 필요합니다.' },
          requestId: crypto.randomUUID(),
        },
        { status: 401 },
      ),
    );
    fireEvent.focus(window);
    expect(
      await screen.findByRole('link', { name: '로그인' }),
    ).toBeInTheDocument();
    expect(screen.queryByText(result.answer)).not.toBeInTheDocument();
    expect(
      screen.queryByText('현재 공개된 사람 찾아줘'),
    ).not.toBeInTheDocument();
    expect(app.validations).toHaveLength(2);
  });

  it('distinguishes empty results and rejects oversized pasted messages without truncation', async () => {
    const app = await setup();
    const input = screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' });
    fireEvent.change(input, { target: { value: '가'.repeat(1001) } });
    expect(
      screen.getByRole('button', { name: '메시지 보내기' }),
    ).toBeDisabled();
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(app.streams).toHaveLength(0);
    expect(input).toHaveValue('가'.repeat(1001));
    fireEvent.change(input, { target: { value: '' } });
    const stream = await app.send();
    await app.finish(
      stream,
      {
        ...result,
        answer: '요청한 조건에 맞는 자료를 찾지 못했어요.',
        cards: [],
      },
      'empty',
    );
    expect(screen.getByText(/조건에 맞는 결과가 없어요/)).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /공개 추천 대상/ }),
    ).not.toBeInTheDocument();
  });
  it('cannot resurrect an answer when stop wins against an in-flight result validation', async () => {
    const app = await setup();
    const stream = await app.send();
    const waiting = deferred<Response>();
    app.validation(() => waiting.promise);
    await act(async () => {
      stream.emit('result', { result });
      stream.emit('done', { status: 'succeeded' });
    });
    await waitFor(() => expect(app.validations).toHaveLength(1));
    await app.user.click(screen.getByRole('button', { name: '응답 중지' }));
    await waitFor(() => expect(app.cancellations).toHaveLength(1));
    await act(async () =>
      waiting.resolve(Response.json({ data: { valid: true, result } })),
    );
    expect(screen.queryByText(result.answer)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /공개 추천 대상/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '답변 복사' }),
    ).not.toBeInTheDocument();
  });

  it('does not expire a fresh same-account login when an old validation returns 401', async () => {
    const app = await setup();
    await app.finish(await app.send());
    const waiting = deferred<Response>();
    app.validation(() => waiting.promise);
    fireEvent.focus(window);
    await waitFor(() => expect(app.validations).toHaveLength(2));
    await app.user.click(
      screen.getByRole('button', { name: '같은 계정 재로그인' }),
    );
    await waitFor(() =>
      expect(screen.getByText('어떤 도전을 찾고 있나요?')).toBeInTheDocument(),
    );
    await act(async () =>
      waiting.resolve(
        Response.json(
          {
            error: { code: 'UNAUTHENTICATED', message: '이전 세션 만료' },
            requestId: crypto.randomUUID(),
          },
          { status: 401 },
        ),
      ),
    );
    expect(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
    ).toBeInTheDocument();
    expect(screen.queryByText(result.answer)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: '로그인' }),
    ).not.toBeInTheDocument();
  });

  it('keeps the input when the conversation context reaches its budget', async () => {
    const app = await setup();
    for (let index = 0; index < 12; index++) {
      fireEvent.change(
        screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
        { target: { value: '가'.repeat(1000) } },
      );
      await app.user.click(
        screen.getByRole('button', { name: '메시지 보내기' }),
      );
      await waitFor(() => expect(app.streams).toHaveLength(index + 1));
      await app.finish(app.streams[index]!, { ...result, cards: [] });
    }
    const draft = '이 입력은 자르거나 보내지 않고 보관합니다.';
    fireEvent.change(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
      { target: { value: draft } },
    );
    await app.user.click(screen.getByRole('button', { name: '메시지 보내기' }));
    expect(screen.getByRole('alert')).toHaveTextContent('대화가 길어졌어요');
    expect(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
    ).toHaveValue(draft);
    expect(app.streams).toHaveLength(12);
  });

  it('explains an unconfigured AI service without generating a demo answer', async () => {
    const app = await setup();
    app.startError(
      Response.json(
        {
          error: { code: 'AI_NOT_CONFIGURED', message: 'AI unavailable' },
          requestId: crypto.randomUUID(),
        },
        { status: 503 },
      ),
    );
    fireEvent.change(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
      { target: { value: '공모전 찾아줘' } },
    );
    await app.user.click(screen.getByRole('button', { name: '메시지 보내기' }));
    expect(
      await screen.findByText(/AI 연결이 아직 준비되지 않았어요/),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '같은 내용으로 다시 요청' }),
    ).toBeInTheDocument();
    expect(app.streams).toHaveLength(0);
    expect(app.validations).toHaveLength(0);
    expect(screen.queryByText(/모의 응답 모드/)).not.toBeInTheDocument();
  });
  it('keeps an answer hidden when blur supersedes an in-flight validation', async () => {
    const app = await setup();
    await app.finish(await app.send());
    const waiting = deferred<Response>();
    app.validation(() => waiting.promise);
    fireEvent.focus(window);
    await waitFor(() => expect(app.validations).toHaveLength(2));
    fireEvent.blur(window);
    await act(async () =>
      waiting.resolve(Response.json({ data: { valid: true, result } })),
    );
    expect(screen.queryByText(result.answer)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /공개 추천 대상/ }),
    ).not.toBeInTheDocument();
    app.validation(async () =>
      Response.json({ data: { valid: false, result: null } }),
    );
    fireEvent.focus(window);
    expect(
      await screen.findByText(/정보나 접근 권한이 바뀌어/),
    ).toBeInTheDocument();
  });

  it('does not replace a confirmed cancellation with an older pending status response', async () => {
    const app = await setup();
    const stream = await app.send();
    const waiting = deferred<Response>();
    const pending = app.views.get(stream.input.requestId)!;
    let queried = false;
    app.statusResponse(() => {
      queried = true;
      return waiting.promise;
    });
    await act(async () => stream.end());
    await waitFor(() => expect(queried).toBe(true));
    await app.user.click(screen.getByRole('button', { name: '응답 중지' }));
    expect(await screen.findByText('응답을 중지했어요.')).toBeInTheDocument();
    await act(async () => waiting.resolve(Response.json({ data: pending })));
    expect(screen.getByText('응답을 중지했어요.')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '상태 확인' }),
    ).not.toBeInTheDocument();
  });
});
