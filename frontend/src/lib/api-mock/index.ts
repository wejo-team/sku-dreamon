/**
 * [참조 출처]
 * 1. docs/api/conventions.md#types - /api/v1 아래 리소스 경로
 * 2. docs/api/README.md - 문서 영역별 현재 구현 범위(AI 미구현)
 * 3. docs/development/frontend.md - 「API와 query」 기능별 endpoint 호출은 features/<기능>/api.ts
 * 4. docs/api/conventions.md#csrf-transport - 상태 변경 요청의 X-CSRF-Token 검사, 실패는 403 FORBIDDEN
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
import { registerNotificationRoutes } from '@/lib/api-mock/handlers-notifications';
import { resetCsrfToken } from '@/lib/api';
import { errorResponse } from '@/lib/api-mock/http';
import { resetMockDatabase, state } from '@/lib/api-mock/state';

const router = new MockRouter();
registerAccountRoutes(router);
registerTeamRoutes(router);
registerApplicationRoutes(router);
registerNotificationRoutes(router);

// [출처 4] 안전 메서드 외 요청은 X-CSRF-Token이 현재 토큰과 같아야 함. 실패는 403 FORBIDDEN
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);
function csrfRejected(method: string, path: string, init: RequestInit) {
  if (SAFE_METHODS.has(method)) return false;
  // 로그아웃은 인증을 먼저 확인합니다(미인증은 라우터가 401로 응답).
  if (path === '/auth/logout' && !state.sessionAccountId) return false;
  const token = new Headers(init.headers).get('X-CSRF-Token');
  return !state.csrfToken || token !== state.csrfToken;
}

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
  const method = (init.method ?? 'GET').toUpperCase();
  if (csrfRejected(method, path, init))
    return errorResponse(
      403,
      'FORBIDDEN',
      '요청을 확인할 수 없어요. 다시 시도해 주세요.',
    );
  return router.handle(method, path, url.searchParams, body);
}

/** 목업 저장소·세션·CSRF 토큰을 초기화합니다. 화면 메모리의 토큰도 함께 버립니다(새로고침과 같음). */
export function resetMockApi(options: { signedIn?: boolean } = {}) {
  resetCsrfToken();
  return resetMockDatabase(options);
}
