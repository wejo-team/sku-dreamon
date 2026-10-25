/**
 * [참조 출처]
 * 1. docs/api/auth.md#account-endpoints - POST /accounts, GET /auth/login-id-availability, POST /auth/login, POST /auth/logout, GET /me
 * 2. docs/api/auth.md#credentials - Credentials { loginId, password }
 * 3. docs/api/auth.md#account - Account { id, loginId, isDemo, hasProfile, schoolVerification, createdAt }
 * 4. docs/api/auth.md#auth-results - SignupResult, LoginResult, LoginIdAvailability
 * 5. docs/api/conventions.md#session-auth - 세션 토큰은 본문에 없고 Set-Cookie로만 전달
 */

import { z } from 'zod';
import { apiRequest, withQuery } from '@/lib/api';
import { Id, Timestamp, success } from '@/lib/api-contract';

const LOGIN_ID = /^[a-z0-9]{4,24}$/;

// [출처 2] 가입·로그인 요청. 정규화는 서버가 다시 수행합니다.
export const Credentials = z
  .object({ loginId: z.string(), password: z.string() })
  .strict();
export type Credentials = z.infer<typeof Credentials>;

// [출처 3] 본인 계정. schoolVerification의 현재 허용값은 unverified 하나
export const Account = z
  .object({
    id: Id,
    loginId: z.string().regex(LOGIN_ID),
    isDemo: z.boolean(),
    hasProfile: z.boolean(),
    schoolVerification: z.literal('unverified'),
    createdAt: Timestamp,
  })
  .strict();
export type Account = z.infer<typeof Account>;

// [출처 4]
export const SignupResult = z.object({ account: Account }).strict();
export type SignupResult = z.infer<typeof SignupResult>;
export const LoginResult = z.object({ account: Account }).strict();
export type LoginResult = z.infer<typeof LoginResult>;
export const LoginIdAvailability = z
  .object({
    normalizedLoginId: z.string().regex(LOGIN_ID),
    available: z.boolean(),
  })
  .strict();
export type LoginIdAvailability = z.infer<typeof LoginIdAvailability>;

// [출처 1, 5] POST /accounts → 201 Success<SignupResult>. 성공 시 서버가 Set-Cookie로 자동 로그인
export async function createAccount(body: Credentials, signal?: AbortSignal) {
  const response = await apiRequest('/accounts', {
    method: 'POST',
    json: Credentials.parse(body),
    signal,
  });
  return success(SignupResult).parse(response).data;
}

// [출처 1] GET /auth/login-id-availability?loginId= → 200 Success<LoginIdAvailability>
export async function getLoginIdAvailability(
  loginId: string,
  signal?: AbortSignal,
) {
  const response = await apiRequest(
    withQuery('/auth/login-id-availability', { loginId }),
    { signal },
  );
  return success(LoginIdAvailability).parse(response).data;
}

// [출처 1, 5] POST /auth/login → 200 Success<LoginResult>. 실패는 401 INVALID_CREDENTIALS
export async function login(body: Credentials, signal?: AbortSignal) {
  const response = await apiRequest('/auth/login', {
    method: 'POST',
    json: Credentials.parse(body),
    signal,
  });
  return success(LoginResult).parse(response).data;
}

// [출처 1] POST /auth/logout → 204 본문 없음
export async function logout(signal?: AbortSignal) {
  await apiRequest('/auth/logout', { method: 'POST', signal });
}

// [출처 1, 3] GET /me → 200 Success<Account>. 미인증은 401 UNAUTHENTICATED
export async function getMe(signal?: AbortSignal) {
  return success(Account).parse(await apiRequest('/me', { signal })).data;
}
