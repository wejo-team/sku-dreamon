// 이전 세션의 늦은 프로필 저장 응답이 현재 계정의 캐시를 덮어쓰지 않아야 합니다.
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import { useSaveVisibility } from '@/features/profiles/queries';
import { createDemoRecords } from '@/features/demo/fixtures';
import { createQueryClient } from '@/lib/query-client';
import { queryKeys } from '@/lib/query-keys';
import { resetCsrfToken } from '@/lib/api';

it.each(['expired', 'switched'])(
  'ignores a late profile write after the session is %s',
  async (state) => {
    const db = createDemoRecords();
    const oldProfile = db.profiles.find(
      (profile) => profile.accountId === db.account.id,
    )!;
    const nextProfile = db.profiles.find(
      (profile) => profile.accountId !== db.account.id,
    )!;
    const client = createQueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    client.setQueryData(queryKeys.me, db.account);
    let complete!: (response: Response) => void;
    resetCsrfToken();
    vi.stubGlobal('fetch', (input: string) =>
      String(input).endsWith('/auth/csrf')
        ? Promise.resolve(Response.json({ data: { csrfToken: 'test-csrf' } }))
        : new Promise<Response>((resolve) => {
            complete = resolve;
          }),
    );
    const hook = renderHook(() => useSaveVisibility(), {
      wrapper: ({ children }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    });
    let saving!: Promise<unknown>;
    act(() => {
      saving = hook.result.current.mutateAsync({
        expectedVersion: oldProfile.version,
        isPublic: true,
      });
    });
    await waitFor(() => expect(complete).toBeDefined());
    const current = state === 'expired' ? null : nextProfile;
    client.setQueryData(
      queryKeys.me,
      current ? { ...db.account, id: current.accountId } : null,
    );
    client.setQueryData(queryKeys.myProfile, current);
    await act(async () => {
      complete(Response.json({ data: { ...oldProfile, isPublic: true } }));
      await saving;
    });
    expect(client.getQueryData(queryKeys.myProfile)).toEqual(current);
    hook.unmount();
    client.clear();
  },
);
