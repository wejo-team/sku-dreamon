/**
 * [참조 출처]
 * 1. docs/api/conventions.md#pagination - 페이지 보정·빈 결과 page=1,totalPages=0, 범위 밖 422
 * 2. docs/api/conventions.md#versioned-action - VERSION_CONFLICT, 생성 재전송 200·다른 본문 REQUEST_ID_REUSED
 * 3. docs/api/conventions.md#errors - 401·403·404·409·422 구분
 * 4. docs/api/applications.md#transitions - 선발 시 같은 공모전의 다른 대기 지원 폐기·정원 충족 시 마감
 * 5. docs/api/notifications.md#notification-fields - unreadCount는 필터와 무관, 읽음은 전부 성공 또는 전부 실패
 * 7. docs/development/testing.md - 「의미 있는 테스트」 권한·검증 규칙·오류 처리·데이터 무결성
 *
 * 목업 어댑터가 계약의 응답 구조와 업무 규칙을 지키는지, 실제 API 모듈(Zod 검증 포함)을 통해 확인합니다.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { mockFetch, resetMockApi } from '@/lib/api-mock';
import * as applications from '@/features/applications/api';
import * as auth from '@/features/auth/api';
import * as contests from '@/features/contests/api';
import * as notifications from '@/features/notifications/api';
import * as profiles from '@/features/profiles/api';
import * as teams from '@/features/teams/api';
import { demoIds } from '@/features/demo/fixtures';
import { ApiError } from '@/lib/api';
import { vi } from 'vitest';

const ids = demoIds;

beforeEach(() => {
  resetMockApi();
  // 실제 fetch 대신 목업 어댑터로 보냅니다(VITE_API_MOCK과 같은 경로).
  vi.stubGlobal('fetch', (input: string, init: RequestInit) =>
    mockFetch(input, init),
  );
});

const code = async (promise: Promise<unknown>) => {
  const error = await promise.then(
    () => null,
    (reason: unknown) => reason,
  );
  expect(error).toBeInstanceOf(ApiError);
  return { status: (error as ApiError).status, code: (error as ApiError).code };
};

async function signIn() {
  return auth.login({
    loginId: 'DreamOnDemo ',
    password: 'DreamonReview2026!',
  });
}

describe('mock API adapter', () => {
  it('accepts an eight-character signup password with a symbol and rejects one without it', async () => {
    await expect(
      auth.createAccount({ loginId: 'shortpassword', password: 'abcdefgh' }),
    ).rejects.toMatchObject({ status: 422 });
    const { account } = await auth.createAccount({
      loginId: 'shortpassword',
      password: 'abcdefg!',
    });
    await auth.logout();
    await expect(
      auth.login({ loginId: 'shortpassword', password: 'abcdefg!' }),
    ).resolves.toMatchObject({ account: { id: account.id } });
  });

  it('logs in with the public demo credentials and rejects others without revealing which part was wrong', async () => {
    expect(await code(auth.getMe())).toEqual({
      status: 401,
      code: 'UNAUTHENTICATED',
    });
    expect(
      await code(
        auth.login({ loginId: 'dreamondemo', password: 'wrong-password-123' }),
      ),
    ).toEqual({ status: 401, code: 'INVALID_CREDENTIALS' });
    const { account } = await signIn();
    expect(account.loginId).toBe('dreamondemo');
    await expect(auth.getMe()).resolves.toMatchObject({ id: ids.accounts.me });
    await auth.logout();
    expect(await code(auth.getMe())).toEqual({
      status: 401,
      code: 'UNAUTHENTICATED',
    });
  });

  it('pages, filters and corrects an out-of-range page', async () => {
    const all = await contests.listContests({ pageSize: 3 });
    expect(all.pagination).toEqual({
      page: 1,
      pageSize: 3,
      total: 7,
      totalPages: 3,
    });
    // 마지막 페이지를 넘으면 마지막 유효 페이지로 보정
    const corrected = await contests.listContests({ pageSize: 3, page: 99 });
    expect(corrected.pagination.page).toBe(3);
    const empty = await contests.listContests({ q: '존재하지 않는 공고' });
    expect(empty).toEqual({
      data: [],
      pagination: { page: 1, pageSize: 20, total: 0, totalPages: 0 },
    });
    expect(await code(contests.listContests({ pageSize: 101 }))).toEqual({
      status: 422,
      code: null,
    });
    const scheduled = await contests.listContests({
      registrationStatus: 'scheduled',
    });
    expect(scheduled.data.map((item) => item.id)).toEqual([
      ids.contests.upcoming,
    ]);
  });

  it.each([
    [
      'created_desc',
      (left: contests.ContestSummary, right: contests.ContestSummary) =>
        right.createdAt.localeCompare(left.createdAt) ||
        right.id.localeCompare(left.id),
    ],
    [
      'deadline_asc',
      (left: contests.ContestSummary, right: contests.ContestSummary) =>
        left.endsAt.localeCompare(right.endsAt) ||
        left.id.localeCompare(right.id),
    ],
  ] as const)(
    'places closed contests last in %s and keeps each group in the sort order',
    async (sort, compare) => {
      const { data } = await contests.listContests({ sort, pageSize: 100 });
      const closed = data.filter(
        (item) => item.registrationStatus === 'closed',
      );
      const others = data.filter(
        (item) => item.registrationStatus !== 'closed',
      );
      expect(closed.length).toBeGreaterThan(0);
      expect(others.length).toBeGreaterThan(0);
      expect(data).toEqual([
        ...[...others].sort(compare),
        ...[...closed].sort(compare),
      ]);
    },
  );

  it('keeps private profiles out of the people directory and its detail', async () => {
    await signIn();
    const people = await profiles.listPeople();
    expect(
      people.data.every((person) => person.accountId !== ids.accounts.me),
    ).toBe(true);
    expect(await code(profiles.getPerson(ids.accounts.minjun))).toEqual({
      status: 404,
      code: 'RESOURCE_NOT_FOUND',
    });
  });

  it('rejects a stale profile version and accepts the current one', async () => {
    await signIn();
    const profile = await profiles.getMyProfile();
    expect(
      await code(
        profiles.putMyProfileVisibility({
          expectedVersion: '9',
          isPublic: true,
        }),
      ),
    ).toEqual({ status: 409, code: 'VERSION_CONFLICT' });
    const saved = await profiles.putMyProfileVisibility({
      expectedVersion: profile.version,
      isPublic: true,
    });
    expect(saved).toMatchObject({ isPublic: true, version: '2' });
  });

  it('replays the same team creation with 200 and rejects a reused request ID with a different body', async () => {
    await signIn();
    const body: teams.TeamCreate = {
      requestId: '11111111-1111-4111-8111-111111111111',
      contestId: ids.contests.openLab,
      name: '열린 실험 팀',
      introduction: '열린 실험실에 함께 참가할 팀원을 찾아요.',
      capacity: '3',
      roleCodes: ['planning'],
      recruitmentDeadline: { date: '2026-11-20', time: null, timeZone: null },
    };
    const first = await teams.createTeam(body);
    expect(first.created).toBe(true);
    expect(first.team).toMatchObject({
      memberCount: 1,
      isDemo: false,
      ownerAccountId: ids.accounts.me,
    });
    const resend = await teams.createTeam(body);
    expect(resend).toMatchObject({
      created: false,
      team: { id: first.team.id },
    });
    expect(
      await code(teams.createTeam({ ...body, name: '다른 이름' })),
    ).toEqual({ status: 409, code: 'REQUEST_ID_REUSED' });
  });

  it('enforces team-space membership and leader-only recruitment actions', async () => {
    await signIn();
    expect(await code(teams.getTeamSpace(ids.teams.makers))).toEqual({
      status: 403,
      code: 'FORBIDDEN',
    });
    const space = await teams.getTeamSpace(ids.teams.greenwave);
    expect(space.viewerRole).toBe('leader');
    expect(space.pendingApplicationCount).toBe(2);
    expect(
      await code(
        teams.closeRecruitment(ids.teams.localcrew, { expectedVersion: '2' }),
      ),
    ).toEqual({ status: 403, code: 'FORBIDDEN' });
  });

  it('hides applications outside the relationship and blocks private-profile applications', async () => {
    // 관계가 없는 새 계정에게는 지원서 존재 자체를 숨김(404)
    await auth.createAccount({
      loginId: 'outsider1',
      password: 'outsider-password-1',
    });
    expect(
      await code(applications.getApplication(ids.applications.localcrew)),
    ).toEqual({
      status: 404,
      code: 'APPLICATION_NOT_FOUND',
    });
    await auth.logout();
    await signIn();
    const created = applications.createApplication(ids.teams.makers, {
      requestId: '22222222-2222-4222-8222-222222222222',
      roleCode: 'planning',
      message: '함께하고 싶어요.',
    });
    expect(await code(created)).toEqual({
      status: 409,
      code: 'PROFILE_PRIVATE',
    });
  });

  it('selects an applicant, fills the team and closes recruitment at capacity', async () => {
    await signIn();
    const first = await applications.selectApplication(
      ids.applications.seoyeon,
      { expectedVersion: '2' },
    );
    expect(first.team.memberCount).toBe(3);
    expect(first.application.status).toBe('selected');
    const second = await applications.selectApplication(ids.applications.sua, {
      expectedVersion: '2',
    });
    expect(second.team).toMatchObject({
      memberCount: 4,
      recruitmentState: 'closed',
      closedReason: 'capacity_reached',
      isRecruiting: false,
    });
    // 같은 버전의 재요청은 이미 선발된 동일 소속이므로 no-op
    const replay = await applications.selectApplication(ids.applications.sua, {
      expectedVersion: '3',
    });
    expect(replay.membershipId).toBe(second.membershipId);
  });

  it('keeps the total unread count independent of the list filter and reads all-or-nothing', async () => {
    await signIn();
    const list = await notifications.listMyNotifications({
      unreadOnly: true,
      pageSize: 1,
    });
    expect(list.data).toHaveLength(1);
    expect(list.unreadCount).toBe(3);
    expect(
      await code(
        notifications.readNotifications({
          notificationIds: [
            ids.notifications.seoyeonApplied,
            '99999999-9999-4999-8999-999999999999',
          ],
        }),
      ),
    ).toEqual({ status: 404, code: 'RESOURCE_NOT_FOUND' });
    expect((await notifications.getUnreadNotificationCount()).unreadCount).toBe(
      3,
    );
    const result = await notifications.readNotifications({
      notificationIds: [
        ids.notifications.seoyeonApplied,
        ids.notifications.suaApplied,
      ],
    });
    expect(result.unreadCount).toBe(1);
  });
});
