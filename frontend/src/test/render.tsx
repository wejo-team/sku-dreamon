/**
 * [참조 출처]
 * 1. docs/development/testing.md - 「의미 있는 테스트」 사용자 동작 검증, API 계약은 실제 요청·응답으로 검사
 * 2. docs/development/frontend.md - 「API와 query」 서버 데이터는 TanStack Query
 *
 * 화면 조각용 공급자·테스트 버튼 컴포넌트는 test/providers.tsx에 있습니다.
 *
 * 화면 테스트 도우미입니다. 화면은 실제 API 함수(features/<기능>/api.ts)로 요청하고,
 * fetch를 목업 어댑터(lib/api-mock)로 연결해 목업 저장소의 데이터로 응답받습니다.
 */

import { act, render, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router';
import { expect, vi } from 'vitest';
import { AiChatProvider } from '@/features/ai/AiChatPage';
import { CatalogGate } from '@/features/catalogs/CatalogGate';
import {
  createDemoRecords,
  demoIds,
  type DemoDatabase,
} from '@/features/demo/fixtures';
import type { Profile } from '@/features/profiles/api';
import { ApplicantReviewProvider } from '@/features/teams/ApplicantReviewProvider';
import { mockFetch, resetMockApi } from '@/lib/api-mock';
import { db, state } from '@/lib/api-mock/state';

export { demoIds };
export const ME = demoIds.accounts.me;

export type ApiRenderOptions = {
  /** 시작 경로(MemoryRouter initialEntries) */
  path?: string;
  /** 목업 세션을 로그인 상태로 시작 */
  signedIn?: boolean;
  /** 목업 저장소 시작값(기본: 목업 원본 사본) */
  db?: DemoDatabase;
  /** true를 돌려주는 요청은 409 VERSION_CONFLICT로 실패시킵니다(서버 충돌 재현). */
  fail?: (request: RecordedRequest) => boolean;
};

/** 화면이 보낸 요청(CSRF 토큰 조회 제외) */
export type RecordedRequest = { method: string; path: string; body: unknown };
export const sentRequests: RecordedRequest[] = [];

/** 목업 서버를 초기화하고 fetch를 목업 어댑터로 연결합니다. */
export function startMockApi({
  signedIn = false,
  db,
  fail,
}: ApiRenderOptions = {}) {
  resetMockApi({ signedIn, db });
  sentRequests.length = 0;
  vi.stubGlobal('fetch', (input: string, init: RequestInit = {}) => {
    const path = new URL(input, 'http://test.invalid').pathname.replace(
      /^\/api\/v1/,
      '',
    );
    const request = {
      method: init.method ?? 'GET',
      path,
      body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
    };
    if (path !== '/auth/csrf') sentRequests.push(request);
    if (fail?.(request))
      return Promise.resolve(
        Response.json(
          {
            error: {
              code: 'VERSION_CONFLICT',
              message: '정보가 변경되었습니다.',
            },
            requestId: 'test',
          },
          { status: 409 },
        ),
      );
    return mockFetch(input, init);
  });
}

/** 테스트마다 새 QueryClient(재시도 없음)로 화면을 그립니다. */
export function renderWithApi(ui: ReactNode, options: ApiRenderOptions = {}) {
  startMockApi(options);
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[options.path ?? '/']}>
        <CatalogGate>
          <AiChatProvider>
            <ApplicantReviewProvider>{ui}</ApplicantReviewProvider>
          </AiChatProvider>
        </CatalogGate>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...view, client };
}

/** 현재 목업 저장소(테스트에서 결과 확인·상태 변경용) */
export const mockDb = () => db();
/** 목업 세션 계정 ID(null이면 비로그인) */
export const mockSession = () => state.sessionAccountId;

/** 특정 계정의 프로필을 바꾼 저장소 사본 */
export function withProfile(
  records: DemoDatabase,
  accountId: string,
  patch: Partial<Profile>,
): DemoDatabase {
  return {
    ...records,
    profiles: records.profiles.map((item) =>
      item.accountId === accountId ? { ...item, ...patch } : item,
    ),
  };
}

/** 본인 프로필을 바꾼 새 목업 저장소 */
export const recordsWithMyProfile = (patch: Partial<Profile>) =>
  withProfile(createDemoRecords(), ME, patch);

/** 목업 저장소의 본인 프로필 */
export const myProfile = () =>
  db().profiles.find((item) => item.accountId === ME)!;

/**
 * 진행 중인 요청·mutation이 모두 끝날 때까지 기다립니다.
 * 앞 요청의 결과로 다음 요청이 시작될 수 있어, 몇 번의 렌더 주기 동안 계속 비어 있을 때 끝난 것으로 봅니다.
 */
export async function settled(client: QueryClient) {
  const busy = () => client.isFetching() + client.isMutating();
  for (let quiet = 0; quiet < 3;) {
    await waitFor(() => expect(busy()).toBe(0));
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)));
    quiet = busy() === 0 ? quiet + 1 : 0;
  }
}
