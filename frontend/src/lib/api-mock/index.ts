/**
 * [참조 출처]
 * 1. docs/api/conventions.md#types - /api/v1 아래 리소스 경로
 * 2. docs/api/README.md - 제품 API 미구현 상태의 설계 초안
 * 3. docs/development/frontend.md - 「API와 query」 기능별 endpoint 호출은 features/<기능>/api.ts
 *
 * 백엔드 없이 같은 계약으로 응답하는 fetch 호환 목업입니다. VITE_API_MOCK=true일 때 lib/api.ts가 사용합니다.
 * 실제 서버가 생기면 환경변수만 끄면 되며, 화면·API 모듈 코드는 바꾸지 않습니다.
 */

import { MockRouter } from '@/lib/api-mock/http';
import { registerAccountRoutes } from '@/lib/api-mock/handlers-account';
import {
  registerApplicationRoutes,
  registerTeamRoutes,
} from '@/lib/api-mock/handlers-teams';
import {
  registerNotificationAndAiRoutes,
  resetAiMock,
} from '@/lib/api-mock/handlers-notifications-ai';
import { resetMockDatabase } from '@/lib/api-mock/state';

const router = new MockRouter();
registerAccountRoutes(router);
registerTeamRoutes(router);
registerApplicationRoutes(router);
registerNotificationAndAiRoutes(router);

// [출처 1] fetch(input, init)와 같은 모양. /api/v1 접두사 뒤 경로로 라우팅합니다.
export async function mockFetch(
  input: string,
  init: RequestInit = {},
): Promise<Response> {
  const url = new URL(input, 'http://mock.invalid');
  const path = url.pathname.replace(/^.*?\/api\/v1(?=\/)/, '');
  let body: unknown;
  if (typeof init.body === 'string' && init.body.length) {
    try {
      body = JSON.parse(init.body);
    } catch {
      return new Response(
        JSON.stringify({
          detail: [
            {
              loc: ['body'],
              msg: 'JSON 형식이 아니에요.',
              type: 'json_invalid',
            },
          ],
        }),
        { status: 422, headers: { 'Content-Type': 'application/json' } },
      );
    }
  }
  if (init.signal?.aborted) throw new DOMException('Aborted', 'AbortError');
  return router.handle(
    (init.method ?? 'GET').toUpperCase(),
    path,
    url.searchParams,
    body,
  );
}

/** 목업 저장소·세션·AI 대화를 초기화합니다. */
export function resetMockApi(options: { signedIn?: boolean } = {}) {
  resetAiMock();
  return resetMockDatabase(options);
}
