// 실제 API 함수와 SSE 파서를 통과하며 외부 모델은 호출하지 않습니다.
import { act, render, screen, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { setupUser } from '@/test/user';
import { createQueryClient } from '@/lib/query-client';
import { advanceSessionGeneration, queryKeys } from '@/lib/query-keys';
import { resetCsrfToken } from '@/lib/api';
import type { Account } from '@/features/auth/api';
import type {
  ApplicantRecommendationResult,
  ApplicantReviewResult,
} from '@/features/ai/contract';
import { createDemoRecords, demoIds } from '@/features/demo/fixtures';
import { ApplicantReview } from './ApplicantReview';
import { TargetAiPanel } from './TargetAiPanel';
import { TeamApplicantRecommendations } from './TeamApplicantRecommendations';
vi.mock('@/lib/clock', async (original) => ({
  ...(await original<typeof import('@/lib/clock')>()),
  isMockApi: false,
}));
const target = '00000000-0000-4000-8000-000000000111';
const person = '00000000-0000-4000-8000-000000000112';
const account: Account = {
  id: '00000000-0000-4000-8000-000000000113',
  loginId: 'leader',
  hasProfile: true,
  schoolVerification: 'unverified',
  createdAt: '2026-10-28T00:00:00Z',
};
const version = { accountId: person, usedVersion: '1', currentVersion: '1' };
const review: ApplicantReviewResult = {
  kind: 'applicant_review',
  applicationId: target,
  summary: '지원서의 경험을 검토했습니다.',
  evidence: ['등록한 React 경험'],
  profileVersions: [version],
  isStale: false,
  isSelectionCandidate: false,
  generatedAt: '2026-10-28T00:00:00Z',
};
const recommendations: ApplicantRecommendationResult = {
  kind: 'applicant_recommendation',
  summary: '역할에 맞는 지원자입니다.',
  candidates: [
    {
      applicationId: target,
      reason: '모집 역할과 등록 경험이 일치해요.',
      profileVersion: version,
    },
  ],
  isStale: false,
  generatedAt: '2026-10-28T00:00:00Z',
};
type Request = {
  path: string;
  method: string;
  body: Record<string, unknown>;
  init: RequestInit;
};
let requests: Request[];
function api(handler: (request: Request) => Response | Promise<Response>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const path = url.replace('/api/v1', '');
      if (path === '/auth/csrf')
        return Response.json({ data: { csrfToken: 'test-csrf' } });
      if (path === '/me') return Response.json({ data: account });
      const request = {
        path,
        method: init.method ?? 'GET',
        body: init.body
          ? (JSON.parse(String(init.body)) as Record<string, unknown>)
          : {},
        init,
      };
      requests.push(request);
      return handler(request);
    }),
  );
}
function frame(
  requestId: string,
  event: string,
  sequence: number,
  payload: object = {},
  attempt = 1,
) {
  return `event: ${event}\ndata: ${JSON.stringify({ requestId, attempt, sequence, ...payload })}\n\n`;
}
function complete(
  requestId: string,
  result: ApplicantReviewResult | ApplicantRecommendationResult,
  attempt = 1,
) {
  return (
    frame(requestId, 'started', 1, { purpose: result.kind }, attempt) +
    frame(requestId, 'result', 2, { result }, attempt) +
    frame(
      requestId,
      'done',
      3,
      {
        status:
          result.kind === 'applicant_recommendation' &&
          !result.candidates.length
            ? 'empty'
            : 'succeeded',
      },
      attempt,
    )
  );
}
function sse(value: string) {
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(value));
        controller.close();
      },
    }),
    { headers: { 'Content-Type': 'text/event-stream' } },
  );
}
function error(status: number, code: string) {
  return Response.json(
    {
      error: { code, message: '요청을 처리할 수 없습니다.' },
      requestId: 'trace',
    },
    { status },
  );
}
function requestState(requestId: string, status: string) {
  return Response.json({
    data: {
      id: requestId,
      purpose: 'applicant_review',
      conversationId: null,
      teamId: null,
      applicationId: target,
      attempt: 1,
      status,
      failure: null,
      expiresAt: '2026-10-29T00:00:00Z',
    },
  });
}
function mount(
  purpose: 'applicant_review' | 'applicant_recommendation' = 'applicant_review',
) {
  const client = createQueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
  client.setQueryData(queryKeys.me, account);
  const ui = (revision = '1', visible = true) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>
        {visible && (
          <TargetAiPanel
            purpose={purpose}
            targetId={target}
            revision={revision}
          />
        )}
      </MemoryRouter>
    </QueryClientProvider>
  );
  return { ...render(ui()), client, ui, user: setupUser() };
}
beforeEach(() => {
  requests = [];
  resetCsrfToken();
});

describe('실제 팀 AI 화면', () => {
  it('완료 후 검증하고 복사 시에도 변경되지 않은 최초 DTO를 전송한다', async () => {
    const updated = {
      ...review,
      isStale: true,
      profileVersions: [{ ...version, currentVersion: '2' }],
    };
    api((r) =>
      r.path.endsWith('/validation')
        ? Response.json({ data: { valid: true, result: updated } })
        : sse(complete(String(r.body.requestId), review)),
    );
    const { user } = mount();
    const clipboard = vi
      .spyOn(navigator.clipboard, 'writeText')
      .mockResolvedValue();
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    expect(
      await screen.findByRole('region', { name: 'AI 지원자 검토 결과' }),
    ).toHaveTextContent(review.summary);
    expect(screen.getByText(/검토 이후 프로필이 변경/)).toBeInTheDocument();
    expect(
      screen.getByText(/현재 선발 후보가 아닌 지원서/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '결과 복사' }));
    await screen.findByText('결과를 복사했어요.');
    expect(clipboard).toHaveBeenCalledWith(
      `${review.summary}\n\n${review.evidence[0]}`,
    );
    expect(
      requests
        .filter((r) => r.path.endsWith('/validation'))
        .map((r) => r.body.result),
    ).toEqual([review, review]);
    expect(requests[0]!.path).toBe(`/applications/${target}/ai-reviews/stream`);
    expect(requests[0]!.init.credentials).toBe('include');
    expect(requests.every((r) => r.method === 'POST')).toBe(true);
  });
  it.each([false, true])(
    '추천 후보 링크와 빈 결과(%s)를 표시한다',
    async (empty) => {
      const result = empty
        ? { ...recommendations, candidates: [] }
        : recommendations;
      api((r) =>
        r.path.endsWith('/validation')
          ? Response.json({ data: { valid: true, result } })
          : sse(complete(String(r.body.requestId), result)),
      );
      const { user } = mount('applicant_recommendation');
      await user.click(
        screen.getByRole('button', { name: 'AI 지원자 추천 요청' }),
      );
      await screen.findByRole('region', { name: 'AI 지원자 추천 결과' });
      expect(requests[0]!.path).toBe(
        `/teams/${target}/applicant-recommendations/stream`,
      );
      if (empty)
        expect(
          screen.getByText('현재 추천할 수 있는 지원자가 없어요.'),
        ).toBeInTheDocument();
      else
        expect(
          screen.getByRole('link', { name: '추천 후보 1 지원서 확인' }),
        ).toHaveAttribute('href', `/applicants/${target}`);
      expect(
        screen.queryByRole('button', { name: /선발하기/ }),
      ).not.toBeInTheDocument();
    },
  );
  it('재시도는 동일 requestId와 expectedAttempt를 전송한다', async () => {
    api((r) => {
      if (r.path.endsWith('/validation'))
        return Response.json({ data: { valid: true, result: review } });
      if (r.path.endsWith('/retries/stream'))
        return sse(
          complete(
            (r.body.input as { requestId: string }).requestId,
            review,
            2,
          ),
        );
      const id = String(r.body.requestId);
      return sse(
        frame(id, 'started', 1, { purpose: 'applicant_review' }) +
          frame(id, 'error', 2, {
            failure: {
              code: 'temporary_failure',
              message: '일시적으로 검토하지 못했어요.',
              retryable: true,
            },
          }),
      );
    });
    const { user } = mount();
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    await user.click(
      await screen.findByRole('button', { name: '검토 다시 시도' }),
    );
    await screen.findByRole('region', { name: 'AI 지원자 검토 결과' });
    expect(requests[1]!.body).toEqual({
      expectedAttempt: 1,
      input: requests[0]!.body,
    });
    expect(requests[2]!.body.attempt).toBe(2);
  });
  it('done 없는 종료는 상태를 조회하고 취소할 수 있다', async () => {
    let id = '';
    api((r) => {
      if (r.method === 'GET') return requestState(id, 'pending');
      if (r.path.endsWith('/cancellation')) return requestState(id, 'canceled');
      id = String(r.body.requestId);
      return sse(
        frame(id, 'started', 1, { purpose: 'applicant_review' }) +
          frame(id, 'answer.delta', 2, { text: '미완성 검토' }) +
          frame(id, 'result', 3, { result: review }),
      );
    });
    const { user } = mount();
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    await screen.findByText(/연결이 끊겼지만 요청은 처리 중/);
    expect(screen.queryByText('미완성 검토')).not.toBeInTheDocument();
    expect(screen.queryByText(review.summary)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '요청 취소' }));
    await screen.findByText('요청을 취소했어요.');
    expect(requests.at(-1)).toMatchObject({
      method: 'PUT',
      body: { expectedAttempt: 1 },
    });
  });
  it.each(['pending', 'error'] as const)(
    '연속 상태 확인의 이전 %s 응답은 최신 재시도 가능 상태를 덮지 않는다',
    async (lateResponse) => {
      let id = '';
      let checks = 0;
      let finish: (value: Response) => void = () => {};
      api(async (request) => {
        if (request.method !== 'GET') {
          id = String(request.body.requestId);
          return sse(frame(id, 'started', 1, { purpose: 'applicant_review' }));
        }
        checks++;
        if (checks === 1) return requestState(id, 'pending');
        if (checks === 2)
          return new Promise<Response>((resolve) => {
            finish = resolve;
          });
        const body = await requestState(id, 'failed').json();
        body.data.failure = {
          code: 'temporary_failure',
          message: '다시 검토할 수 있어요.',
          retryable: true,
        };
        return Response.json(body);
      });
      const { user } = mount();
      await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
      await screen.findByText(/연결이 끊겼지만 요청은 처리 중/);
      await user.click(screen.getByRole('button', { name: '요청 상태 확인' }));
      await waitFor(() => expect(checks).toBe(2));
      await user.click(screen.getByRole('button', { name: '요청 상태 확인' }));
      expect(
        await screen.findByRole('button', { name: '검토 다시 시도' }),
      ).toBeEnabled();
      await act(async () => {
        finish(
          lateResponse === 'pending'
            ? requestState(id, 'pending')
            : error(500, 'INTERNAL_ERROR'),
        );
      });
      expect(
        screen.getByRole('button', { name: '검토 다시 시도' }),
      ).toBeEnabled();
      expect(screen.getByText('다시 검토할 수 있어요.')).toBeInTheDocument();
      expect(
        screen.queryByRole('button', { name: '요청 상태 확인' }),
      ).not.toBeInTheDocument();
    },
  );

  it('invalidated 종료는 임시 답변을 전부 제거한다', async () => {
    api((r) => {
      const id = String(r.body.requestId);
      return sse(
        frame(id, 'started', 1, { purpose: 'applicant_review' }) +
          frame(id, 'answer.delta', 2, { text: '폐기할 임시 내용' }) +
          frame(id, 'invalidated', 3, { reason: 'context_changed' }),
      );
    });
    const { user } = mount();
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    await screen.findByText(/지원 정보나 검토 권한이 변경/);
    expect(screen.queryByText('폐기할 임시 내용')).not.toBeInTheDocument();
    expect(requests).toHaveLength(1);
  });
  it('재진입은 원본 DTO로 재검증하고 권한 상실 시 본문과 복사를 숨긴다', async () => {
    let checks = 0;
    api((r) =>
      r.path.endsWith('/validation')
        ? ++checks === 1
          ? Response.json({ data: { valid: true, result: review } })
          : error(404, 'NOT_FOUND')
        : sse(complete(String(r.body.requestId), review)),
    );
    const view = mount();
    await view.user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    await screen.findByRole('region', { name: 'AI 지원자 검토 결과' });
    view.rerender(view.ui('1', false));
    view.rerender(view.ui());
    await screen.findByText(/지원 정보나 검토 권한이 변경/);
    expect(screen.queryByText(review.summary)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '결과 복사' }),
    ).not.toBeInTheDocument();
    expect(requests.at(-1)?.body.result).toEqual(review);
  });
  it('focus와 프로필 버전 변경 시 재검증하고 무효 결과를 제거한다', async () => {
    let valid = true;
    api((r) =>
      r.path.endsWith('/validation')
        ? Response.json({ data: { valid, result: valid ? review : null } })
        : sse(complete(String(r.body.requestId), review)),
    );
    const view = mount();
    await view.user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    await screen.findByRole('region', { name: 'AI 지원자 검토 결과' });
    view.rerender(view.ui('2'));
    await waitFor(() =>
      expect(
        requests.filter((r) => r.path.endsWith('/validation')),
      ).toHaveLength(2),
    );
    valid = false;
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
    });
    await screen.findByText(/지원 정보나 검토 권한이 변경/);
    expect(screen.queryByText(review.summary)).not.toBeInTheDocument();
  });
  it('blur 뒤 늦게 도착한 검증 결과는 다시 표시하지 않고 focus에서 새로 확인한다', async () => {
    let checks = 0;
    let finish: (value: Response) => void = () => {};
    api((request) => {
      if (!request.path.endsWith('/validation'))
        return sse(complete(String(request.body.requestId), review));
      checks++;
      if (checks === 2)
        return new Promise<Response>((resolve) => {
          finish = resolve;
        });
      return Response.json({ data: { valid: true, result: review } });
    });
    const view = mount();
    await view.user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    await screen.findByRole('region', { name: 'AI 지원자 검토 결과' });
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
    });
    await waitFor(() => expect(checks).toBe(2));
    await act(async () => {
      window.dispatchEvent(new Event('blur'));
      finish(Response.json({ data: { valid: true, result: review } }));
    });
    expect(screen.queryByText(review.summary)).not.toBeInTheDocument();
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
    });
    await screen.findByRole('region', { name: 'AI 지원자 검토 결과' });
    expect(checks).toBe(3);
  });

  it('동일 계정 재로그인 뒤 늦은 401은 새 세션을 지우지 않는다', async () => {
    let finish: (value: Response) => void = () => {};
    api(
      () =>
        new Promise<Response>((resolve) => {
          finish = resolve;
        }),
    );
    const view = mount();
    await view.user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    await waitFor(() => expect(requests).toHaveLength(1));
    act(() => {
      advanceSessionGeneration(view.client);
      view.client.setQueryData(queryKeys.me, { ...account });
    });
    view.rerender(view.ui());
    await act(async () => {
      finish(error(401, 'UNAUTHENTICATED'));
    });
    expect(view.client.getQueryData(queryKeys.me)).toEqual(account);
    expect(screen.getByRole('button', { name: 'AI 검토 요청' })).toBeEnabled();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('현재 세션의 검증 401은 인증 상태와 결과를 폐기한다', async () => {
    api((r) =>
      r.path.endsWith('/validation')
        ? error(401, 'UNAUTHENTICATED')
        : sse(complete(String(r.body.requestId), review)),
    );
    const view = mount();
    await view.user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    await waitFor(() =>
      expect(view.client.getQueryData(queryKeys.me)).toBeNull(),
    );
    expect(
      screen.queryByRole('region', { name: 'AI 검토 도움' }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(review.summary)).not.toBeInTheDocument();
  });
  it('503 미설정은 모의 응답으로 전환하지 않는다', async () => {
    api(() => error(503, 'AI_NOT_CONFIGURED'));
    const { user } = mount();
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    await screen.findByText(/AI 서비스가 아직 준비되지 않았어요/);
    expect(screen.queryByText('모의 응답')).not.toBeInTheDocument();
    expect(requests).toHaveLength(1);
  });
  it('팀원은 추천을 볼 수 없으며 종료된 비공개 지원서는 검토할 수 있다', async () => {
    api((r) =>
      r.path.endsWith('/validation')
        ? Response.json({ data: { valid: true, result: review } })
        : sse(complete(String(r.body.requestId), review)),
    );
    const records = createDemoRecords();
    const application = records.applications.find(
      (item) => item.id === demoIds.applications.seoyeon,
    )!;
    const profile = records.profiles.find(
      (item) => item.accountId === application.applicantAccountId,
    )!;
    const client = createQueryClient({
      defaultOptions: { queries: { retry: false, staleTime: Infinity } },
    });
    client.setQueryData(queryKeys.me, account);
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <TeamApplicantRecommendations
            teamId={target}
            revision="1"
            isLeader={false}
          />
          <ApplicantReview
            application={{ ...application, status: 'discarded' }}
            profile={{ ...profile, isPublic: false }}
            mayReviewExistingApplication
          />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      screen.queryByRole('region', { name: 'AI 지원자 추천' }),
    ).not.toBeInTheDocument();
    const user = setupUser();
    await user.click(screen.getByRole('button', { name: 'AI 검토 요청' }));
    await screen.findByRole('region', { name: 'AI 지원자 검토 결과' });
    expect(requests[0]!.path).toBe(
      `/applications/${application.id}/ai-reviews/stream`,
    );
  });
});
