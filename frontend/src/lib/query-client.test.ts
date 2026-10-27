// 인증 실패와 일반 오류를 구분하고, 취소된 이전 세션 요청의 늦은 응답을 검증합니다.
import { describe, expect, it } from 'vitest';
import { ApiError } from '@/lib/api';
import { createQueryClient } from '@/lib/query-client';
import { queryKeys } from '@/lib/query-keys';

const apiError = (status: number, code: string) =>
  new ApiError(status, {
    error: { code, message: '테스트 오류' },
    requestId: 'test',
  });
const clientWithSession = () => {
  const client = createQueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  client.setQueryData(queryKeys.me, { id: 'current-account' });
  client.setQueryData(queryKeys.myProfile, { realName: '개인 정보' });
  return client;
};

describe('session expiry cache handling', () => {
  it('clears personal data and cancels late queries without restoring the expired session', async () => {
    const client = clientWithSession();
    let finish!: (value: string) => void;
    const late = client
      .fetchQuery({
        queryKey: ['applications', 'late'],
        queryFn: () =>
          new Promise<string>((resolve) => {
            finish = resolve;
          }),
      })
      .catch(() => undefined);
    let finishMe!: (value: { id: string }) => void;
    const lateMe = client
      .fetchQuery({
        queryKey: queryKeys.me,
        queryFn: () =>
          new Promise<{ id: string }>((resolve) => {
            finishMe = resolve;
          }),
      })
      .catch(() => undefined);
    await expect(
      client.fetchQuery({
        queryKey: ['teams', 'expired'],
        queryFn: () => {
          throw apiError(401, 'UNAUTHENTICATED');
        },
      }),
    ).rejects.toMatchObject({ status: 401 });
    await Promise.all([late, lateMe]);
    finishMe({ id: 'old-session' });
    finish('이전 계정의 늦은 응답');
    await Promise.resolve();
    expect(client.getQueryData(queryKeys.me)).toBeNull();
    expect(client.getQueryData(queryKeys.myProfile)).toBeUndefined();
    expect(client.getQueryData(['applications', 'late'])).toBeUndefined();
    expect(client.isFetching()).toBe(0);
    client.clear();
  });

  it('also expires the session on an unauthenticated mutation without retrying it', async () => {
    const client = clientWithSession();
    let attempts = 0;
    const mutation = client.getMutationCache().build(client, {
      mutationFn: async () => {
        attempts++;
        throw apiError(401, 'UNAUTHENTICATED');
      },
    });
    await expect(mutation.execute(undefined)).rejects.toMatchObject({
      status: 401,
    });
    expect(attempts).toBe(1);
    expect(client.getQueryData(queryKeys.me)).toBeNull();
    expect(client.getQueryData(queryKeys.myProfile)).toBeUndefined();
    client.clear();
  });

  it.each([
    [401, 'INVALID_CREDENTIALS'],
    [403, 'FORBIDDEN'],
    [404, 'NOT_FOUND'],
    [503, 'UNAVAILABLE'],
  ] as const)('preserves the session after %s %s', async (status, code) => {
    const client = clientWithSession();
    const mutation = client.getMutationCache().build(client, {
      mutationFn: async () => {
        throw apiError(status, code);
      },
    });
    await expect(mutation.execute(undefined)).rejects.toMatchObject({ status });
    expect(client.getQueryData(queryKeys.me)).toEqual({
      id: 'current-account',
    });
    expect(client.getQueryData(queryKeys.myProfile)).toBeDefined();
    client.clear();
  });
});
