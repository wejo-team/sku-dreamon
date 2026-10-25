/**
 * [참조 출처]
 * 1. docs/api/conventions.md#types - /api/v1 접두사, application/json camelCase 본문
 * 2. docs/api/conventions.md#success-responses - 본문 있는 성공은 최상위 data, 204는 본문 없음, 202의 Location 헤더
 * 3. docs/api/conventions.md#session-auth - 서버 세션 쿠키 전달, 토큰을 JS·localStorage로 관리하지 않음
 * 4. docs/api/conventions.md#errors - Error{error{code,message},requestId}, ValidationError{detail[]}, 문구가 아닌 코드로 분기
 * 5. docs/development/frontend.md - 「API와 query」 HTTP 실패를 정상 응답으로 취급하지 않음, 204 처리, AbortSignal 전달
 */

import {
  errorSchema,
  validationErrorSchema,
  type ValidationIssue,
} from '@/lib/api-contract';

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(
  /\/$/,
  '',
);

// 백엔드가 없을 때 같은 요청을 목업 어댑터로 보냅니다(lib/api-mock). 운영 빌드에서는 켜지 않습니다.
const useMock = import.meta.env.VITE_API_MOCK === 'true';

// 목업이 꺼져 있으면 fetch를 바로 호출해 요청 시작 시점을 늦추지 않습니다.
function send(input: string, init: RequestInit): Promise<Response> {
  if (!useMock) return fetch(input, init);
  return import('@/lib/api-mock').then(({ mockFetch }) =>
    mockFetch(input, init),
  );
}

// [출처 4] HTTP 실패. 업무 분기는 message가 아닌 code(예: VERSION_CONFLICT)로 합니다.
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;
  /** 공통 Error 본문의 error.code. 422·형식 밖 본문이면 null */
  readonly code: string | null;
  /** 422 ValidationError의 detail[]. 그 외 빈 배열 */
  readonly issues: ValidationIssue[];
  /** 공통 Error 본문의 요청 추적 ID */
  readonly requestId: string | null;

  constructor(status: number, body: unknown) {
    super(`API request failed (${status})`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
    const error = errorSchema.safeParse(body);
    const validation = validationErrorSchema.safeParse(body);
    this.code = error.success ? error.data.error.code : null;
    this.requestId = error.success ? error.data.requestId : null;
    this.issues = validation.success ? validation.data.detail : [];
  }
}

export type ApiRequestOptions = Omit<RequestInit, 'body'> & {
  /** JSON으로 직렬화할 본문. 문자열·FormData 등은 body로 그대로 넘깁니다. */
  json?: unknown;
  body?: RequestInit['body'];
};

export type ApiResponse = {
  status: number;
  headers: Headers;
  body: unknown;
};

// [출처 1, 2, 3, 4, 5] 상태·헤더까지 필요한 호출(201/200 구분, 202 Location)에 사용합니다.
export async function apiRequestWithResponse(
  path: string,
  { json, ...options }: ApiRequestOptions = {},
): Promise<ApiResponse> {
  const headers = new Headers(options.headers);
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');
  const init: RequestInit = {
    ...options,
    headers,
    // [출처 3] 세션은 브라우저가 쿠키로 전달합니다.
    credentials: options.credentials ?? 'include',
  };
  if (json !== undefined) {
    if (!headers.has('Content-Type'))
      headers.set('Content-Type', 'application/json');
    init.body = JSON.stringify(json);
  }

  const response = await send(`${baseUrl}/${path.replace(/^\//, '')}`, init);

  if (!response.ok) {
    const text = await response.text();
    let body: unknown = text;
    try {
      body = JSON.parse(text);
    } catch {
      // Proxy errors may return HTML or text instead of the API's JSON format.
    }
    throw new ApiError(response.status, body);
  }

  // [출처 2] 204는 본문이 없으므로 JSON을 읽지 않습니다.
  if (response.status === 204)
    return { status: 204, headers: response.headers, body: undefined };

  const body: unknown = await response.json();
  return { status: response.status, headers: response.headers, body };
}

export async function apiRequest(
  path: string,
  options: ApiRequestOptions = {},
): Promise<unknown> {
  return (await apiRequestWithResponse(path, options)).body;
}

// query 객체를 문자열로 만듭니다. undefined·null·빈 문자열은 생략(기본값 적용)합니다.
// docs/api/conventions.md#types: CatalogCode 등은 길이 1 이상이라 `fieldCode=`는 유효한 값이 아닙니다.
export function withQuery(
  path: string,
  query: Record<string, string | number | boolean | null | undefined> = {},
) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === '') continue;
    params.set(key, String(value));
  }
  const search = params.toString();
  return search ? `${path}?${search}` : path;
}
