// 인증 만료 시 보호된 캐시를 폐기하고, 일반 오류·잘못된 로그인 정보와 구분합니다.
import {
  MutationCache,
  QueryCache,
  QueryClient,
  type QueryClientConfig,
} from '@tanstack/react-query';
import { ApiError, resetCsrfToken } from '@/lib/api';
import { queryKeys } from '@/lib/query-keys';

export function createQueryClient(config: QueryClientConfig = {}) {
  let expiring = false;
  const expireSession = (error: unknown) => {
    if (
      !(error instanceof ApiError) ||
      error.status !== 401 ||
      error.code !== 'UNAUTHENTICATED' ||
      expiring ||
      !client.getQueryData(queryKeys.me)
    )
      return;
    expiring = true;
    resetCsrfToken();
    const sessionData = {
      predicate: (query: { queryKey: readonly unknown[] }) =>
        ['my', 'applications', 'people'].includes(String(query.queryKey[0])) ||
        (query.queryKey[0] === 'teams' && query.queryKey[1] === 'space'),
    };
    // 취소를 먼저 마쳐 늦게 도착한 이전 세션의 응답이 개인 캐시를 복구하지 못하게 합니다.
    const cancellation = client.cancelQueries({
      predicate: (query) =>
        sessionData.predicate(query) || query.queryKey[0] === 'auth',
    });
    client.setQueryData(queryKeys.me, null);
    void cancellation.then(() => {
      // 활성 observer도 초기 상태를 전달받아 다음 로그인에서 새 query에 다시 연결됩니다.
      // resetQueries의 자동 재조회는 만료된 보호 요청을 반복하므로 사용하지 않습니다.
      client
        .getQueryCache()
        .findAll(sessionData)
        .forEach((query) => query.reset());
      expiring = false;
    });
  };
  const client = new QueryClient({
    ...config,
    queryCache: new QueryCache({ onError: expireSession }),
    mutationCache: new MutationCache({ onError: expireSession }),
  });
  return client;
}

export const queryClient = createQueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: false, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});
