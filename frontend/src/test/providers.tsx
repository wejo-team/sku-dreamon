/**
 * [참조 출처]
 * 1. docs/development/frontend.md - 「API와 query」 서버 데이터는 TanStack Query
 * 2. docs/api/catalogs.md#catalog-endpoints - GET /catalogs, GET /catalogs/academic-units
 *
 * 화면 테스트용 공급자와 버튼 컴포넌트입니다(컴포넌트만 내보내 fast refresh 규칙을 지킵니다).
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { useLogin, useLogout, useSession } from '@/features/auth/queries';
import {
  academicUnitsQueryOptions,
  catalogsQueryOptions,
} from '@/features/catalogs/queries';
import { demoId, demoPassword } from '@/features/demo/auth-policy';
import {
  fixtureAcademicUnits,
  fixtureCatalogs,
} from '@/features/demo/fixtures';

// [출처 2] 선택지(GET /catalogs 목업 응답)를 미리 채운 QueryClient. 네트워크 없이 표시명만 필요한 화면 조각에 씁니다.
function catalogClient() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  client.setQueryData(catalogsQueryOptions.queryKey, fixtureCatalogs());
  client.setQueryData(
    academicUnitsQueryOptions.queryKey,
    fixtureAcademicUnits(),
  );
  return client;
}

/** 선택지 캐시와 라우터만 제공합니다(rerender 사이에도 같은 QueryClient 유지). */
export function CatalogProviders({
  children,
  initialEntries,
}: {
  children: ReactNode;
  initialEntries?: string[];
}) {
  const [client] = useState(catalogClient);
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

/** 테스트용 로그인·로그아웃 버튼(공개 데모 계정, 목업 API 경유) */
export function TestSessionButton() {
  const { signedIn } = useSession();
  const login = useLogin();
  const logout = useLogout();
  return (
    <button
      type="button"
      onClick={() =>
        signedIn
          ? logout.mutate()
          : login.mutate({ loginId: demoId, password: demoPassword })
      }
    >
      {signedIn ? '테스트 로그아웃' : '테스트 로그인'}
    </button>
  );
}
