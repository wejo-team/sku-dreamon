/**
 * [참조 출처]
 * 1. docs/api/auth.md#account-endpoints - GET /me(미인증 401), POST /auth/login, POST /accounts(성공 시 로그인), POST /auth/logout
 * 2. docs/api/conventions.md#csrf-transport - 인증 전환 뒤 CSRF 토큰 폐기(features/auth/api.ts)
 * 3. docs/development/frontend.md - 「API와 query」 서버 데이터와 요청 상태는 TanStack Query
 *
 * 로그인 세션 조회와 가입·로그인·로그아웃 요청입니다. 세션 토큰은 쿠키로만 다루고 JS에 저장하지 않습니다.
 */

import {
  queryOptions,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import {
  createAccount,
  getMe,
  login,
  type Credentials,
  logout,
  type Account,
} from '@/features/auth/api';
import { ApiError } from '@/lib/api';
import { queryKeys, resetSessionData } from '@/lib/query-keys';

// [출처 1] 미인증(401)은 오류가 아니라 비로그인 상태로 봅니다.
export const meQueryOptions = queryOptions({
  queryKey: queryKeys.me,
  queryFn: async ({ signal }): Promise<Account | null> => {
    try {
      return await getMe(signal);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return null;
      throw error;
    }
  },
});

/** 현재 로그인 계정. 확인 중에는 signedIn=false, isPending=true입니다. */
export function useSession() {
  const query = useQuery(meQueryOptions);
  return {
    account: query.data ?? null,
    signedIn: !!query.data,
    isPending: query.isPending,
    isError: query.isError,
    refetch: query.refetch,
  };
}

// [출처 1, 2] 로그인·가입 성공 후 새 세션 기준으로 데이터를 다시 받습니다.
export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Credentials) => login(body),
    onSuccess: async ({ account }) => {
      client.setQueryData(queryKeys.me, account);
      await resetSessionData(client);
    },
  });
}

export function useSignup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Credentials) => createAccount(body),
    onSuccess: async ({ account }) => {
      client.setQueryData(queryKeys.me, account);
      await resetSessionData(client);
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => logout(),
    // 실패(이미 만료 등)해도 화면은 비로그인으로 돌리고 서버 상태를 다시 확인합니다.
    onSettled: async () => {
      client.setQueryData(queryKeys.me, null);
      await resetSessionData(client);
    },
  });
}
