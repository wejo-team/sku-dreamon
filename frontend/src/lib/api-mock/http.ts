/**
 * [참조 출처]
 * 1. docs/api/conventions.md#success-responses - Success·Page 구조와 HTTP 상태, 204 본문 없음, 202 Location
 * 2. docs/api/conventions.md#errors - Error{error{code,message},requestId}, 422 detail[]{loc,msg,type}
 * 3. docs/api/conventions.md#pagination - page·pageSize 기본 1·20, 범위 밖 422, 마지막 페이지 보정, totalPages
 *
 * 목업 서버의 요청 라우팅과 응답 작성 도우미입니다. 실제 서버를 대신하는 개발용 코드이며 운영 빌드에 포함되지 않습니다.
 */

import type { z } from 'zod';
import type { PageMeta } from '@/lib/api-contract';

export type MockContext = {
  method: string;
  path: string;
  params: Record<string, string>;
  query: URLSearchParams;
  body: unknown;
};

export type MockHandler = (
  context: MockContext,
) => Response | Promise<Response>;

type Route = {
  method: string;
  pattern: RegExp;
  keys: string[];
  handler: MockHandler;
};

// [출처 2] 업무 오류를 던지면 라우터가 Error 본문으로 바꿉니다.
export class MockHttpError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export class MockValidationError extends Error {
  constructor(
    readonly issues: { loc: (string | number)[]; msg: string; type: string }[],
  ) {
    super('validation failed');
  }
}

let requestCounter = 0;
const requestId = () => `mock-request-${++requestCounter}`;

// [출처 1]
export const json = (
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
export const ok = (data: unknown, status = 200, headers = {}) =>
  json(status, { data }, headers);
export const noContent = () => new Response(null, { status: 204 });

// [출처 2]
export const errorResponse = (status: number, code: string, message: string) =>
  json(status, { error: { code, message }, requestId: requestId() });

export const fail = (status: number, code: string, message: string): never => {
  throw new MockHttpError(status, code, message);
};
export const notFound = (): never =>
  fail(404, 'RESOURCE_NOT_FOUND', '요청한 정보를 찾을 수 없어요.');
export const forbidden = (): never =>
  fail(403, 'FORBIDDEN', '이 작업을 할 권한이 없어요.');
export const conflict = (code: string, message: string): never =>
  fail(409, code, message);

// [출처 2] Zod 검증 실패 → 422 detail[]. loc는 body·query로 시작
export function validate<T extends z.ZodTypeAny>(
  schema: T,
  value: unknown,
  location: 'body' | 'query' | 'path' = 'body',
): z.infer<T> {
  const result = schema.safeParse(value);
  if (result.success) return result.data;
  throw new MockValidationError(
    result.error.issues.map((issue) => ({
      loc: [location, ...issue.path],
      msg: issue.message,
      type: issue.code,
    })),
  );
}

export const invalid = (loc: (string | number)[], msg: string): never => {
  throw new MockValidationError([{ loc, msg, type: 'value_error' }]);
};

// [출처 3] 공통 페이지 query 해석과 보정
export function paginate<T>(items: T[], query: URLSearchParams) {
  const read = (key: string, fallback: number, max?: number) => {
    const raw = query.get(key);
    if (raw === null) return fallback;
    const value = Number(raw);
    if (
      !/^\d+$/.test(raw) ||
      !Number.isSafeInteger(value) ||
      value < 1 ||
      (max !== undefined && value > max)
    )
      invalid(['query', key], `${key} 값이 올바르지 않아요.`);
    return value;
  };
  const pageSize = read('pageSize', 20, 100);
  const requested = read('page', 1);
  const total = items.length;
  const totalPages = Math.ceil(total / pageSize);
  // 결과가 없으면 1페이지, 마지막 페이지를 넘으면 마지막 유효 페이지로 보정
  const page = totalPages === 0 ? 1 : Math.min(requested, totalPages);
  const pagination: PageMeta = { page, pageSize, total, totalPages };
  return {
    data: items.slice((page - 1) * pageSize, page * pageSize),
    pagination,
  };
}

export function booleanQuery(query: URLSearchParams, key: string) {
  const raw = query.get(key);
  if (raw === null) return false;
  if (raw !== 'true' && raw !== 'false')
    invalid(['query', key], `${key}는 true 또는 false여야 해요.`);
  return raw === 'true';
}

// [출처 3] q: 앞뒤 공백 제거, 빈 문자열은 검색 없음
export const searchText = (query: URLSearchParams) =>
  query.get('q')?.trim().toLowerCase() ?? '';

export class MockRouter {
  private routes: Route[] = [];

  on(method: string, path: string, handler: MockHandler) {
    const keys: string[] = [];
    const pattern = new RegExp(
      `^${path.replace(/\{(\w+)\}/g, (_, key: string) => {
        keys.push(key);
        return '([^/]+)';
      })}$`,
    );
    this.routes.push({ method, pattern, keys, handler });
    return this;
  }

  async handle(
    method: string,
    path: string,
    query: URLSearchParams,
    body: unknown,
  ) {
    let pathMatched = false;
    for (const route of this.routes) {
      const match = route.pattern.exec(path);
      if (!match) continue;
      pathMatched = true;
      if (route.method !== method) continue;
      const params = Object.fromEntries(
        route.keys.map((key, index) => [
          key,
          decodeURIComponent(match[index + 1]!),
        ]),
      );
      try {
        return await route.handler({ method, path, params, query, body });
      } catch (error) {
        if (error instanceof MockHttpError)
          return errorResponse(error.status, error.code, error.message);
        if (error instanceof MockValidationError)
          return json(422, { detail: error.issues });
        throw error;
      }
    }
    return pathMatched
      ? errorResponse(405, 'METHOD_NOT_ALLOWED', '지원하지 않는 메서드예요.')
      : errorResponse(404, 'RESOURCE_NOT_FOUND', '정의되지 않은 경로예요.');
  }
}
