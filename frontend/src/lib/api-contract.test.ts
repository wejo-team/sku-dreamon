/**
 * [참조 출처]
 * 1. docs/api/README.md - 각 영역 문서의 메서드·경로·요청·응답을 프론트와 서버가 같이 검토
 * 2. docs/api/conventions.md#types - 선언하지 않은 필드·snake_case 거부, BIGINT 십진 문자열, null과 생략 구분
 * 3. docs/development/testing.md - 「의미 있는 테스트」 API 계약은 실제 요청·응답으로 검사
 *
 * 영역별 API 함수가 문서의 메서드·경로·query·본문을 그대로 보내는지, 응답이 문서 필드와 다르면 거부하는지 확인합니다.
 */

import { afterEach, describe, expect, it, vi } from 'vitest';
import { resetCsrfToken } from '@/lib/api';
import * as applications from '@/features/applications/api';
import * as auth from '@/features/auth/api';
import * as catalogs from '@/features/catalogs/api';
import * as contests from '@/features/contests/api';
import * as notifications from '@/features/notifications/api';
import * as profiles from '@/features/profiles/api';
import * as teams from '@/features/teams/api';
import {
  createDemoRecords,
  deriveContest,
  deriveTeam,
  demoIds,
  toTeamSummary,
} from '@/features/demo/fixtures';

afterEach(() => {
  vi.unstubAllGlobals();
  resetCsrfToken();
});

const records = createDemoRecords();
const contest = deriveContest(records.contests[0]!, records);
const team = deriveTeam(records.teams[0]!, records);
const application = records.applications[0]!;
const profile = records.profiles[0]!;
const ID = demoIds.teams.makers;
const VERSION = { expectedVersion: '1' };

function respond(
  body: unknown,
  status = 200,
  headers: Record<string, string> = {},
) {
  // docs/api/conventions.md#csrf-transport: 상태 변경 전 토큰 조회(GET /auth/csrf)에는 발급 응답을 줍니다.
  const fetchMock = vi.fn((url: string) =>
    Promise.resolve(
      url.endsWith('/auth/csrf')
        ? Response.json({ data: { csrfToken: 'csrf-token-1' } })
        : status === 204
          ? new Response(null, { status })
          : Response.json(body, { status, headers }),
    ),
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

// 토큰 조회를 뺀 첫 실제 요청
const call = (fetchMock: ReturnType<typeof vi.fn>) => {
  const [url, init] = fetchMock.mock.calls.find(
    ([target]) => !String(target).endsWith('/auth/csrf'),
  )! as [string, RequestInit];
  return {
    url,
    method: init.method ?? 'GET',
    body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
  };
};

const page = (data: unknown[]) => ({
  data,
  pagination: {
    page: 1,
    pageSize: 20,
    total: data.length,
    totalPages: data.length ? 1 : 0,
  },
});

// [출처 1] 메서드·경로·본문이 문서 표와 같은지
describe('endpoint requests match docs/api', () => {
  const account = records.account;
  const cases: [
    string,
    () => Promise<unknown>,
    unknown,
    string,
    string,
    unknown?,
  ][] = [
    [
      'POST /accounts',
      () =>
        auth.createAccount({ loginId: 'newuser', password: 'p'.repeat(15) }),
      { data: { account } },
      'POST',
      '/api/v1/accounts',
      { loginId: 'newuser', password: 'p'.repeat(15) },
    ],
    [
      'GET /auth/login-id-availability',
      () => auth.getLoginIdAvailability('NewUser'),
      { data: { normalizedLoginId: 'newuser', available: true } },
      'GET',
      '/api/v1/auth/login-id-availability?loginId=NewUser',
    ],
    [
      'POST /auth/login',
      () => auth.login({ loginId: 'dreamondemo', password: 'p'.repeat(15) }),
      { data: { account } },
      'POST',
      '/api/v1/auth/login',
      { loginId: 'dreamondemo', password: 'p'.repeat(15) },
    ],
    ['GET /me', () => auth.getMe(), { data: account }, 'GET', '/api/v1/me'],
    [
      'GET /catalogs',
      () => catalogs.getCatalogs(),
      { data: records.catalogs },
      'GET',
      '/api/v1/catalogs',
    ],
    [
      'GET /catalogs/academic-units',
      () => catalogs.getAcademicUnits(),
      { data: records.academicUnits },
      'GET',
      '/api/v1/catalogs/academic-units',
    ],
    [
      'GET /contests',
      () =>
        contests.listContests({
          q: '캠퍼스',
          fieldCode: 'education',
          sort: 'deadline_asc',
          registrationStatus: 'open',
          page: 2,
          pageSize: 6,
        }),
      page([]),
      'GET',
      '/api/v1/contests?q=%EC%BA%A0%ED%8D%BC%EC%8A%A4&fieldCode=education&sort=deadline_asc&registrationStatus=open&page=2&pageSize=6',
    ],
    [
      'GET /contests/{contestId}',
      () => contests.getContest(contest.id),
      { data: contest },
      'GET',
      `/api/v1/contests/${contest.id}`,
    ],
    [
      'GET /me/profile',
      () => profiles.getMyProfile(),
      { data: profile },
      'GET',
      '/api/v1/me/profile',
    ],
    [
      'PUT /me/profile/visibility',
      () =>
        profiles.putMyProfileVisibility({
          expectedVersion: '1',
          isPublic: true,
        }),
      { data: profile },
      'PUT',
      '/api/v1/me/profile/visibility',
      { expectedVersion: '1', isPublic: true },
    ],
    [
      'GET /people',
      () => profiles.listPeople({ roleCode: 'design' }),
      page([]),
      'GET',
      '/api/v1/people?roleCode=design',
    ],
    [
      'GET /people/{accountId}',
      () => profiles.getPerson(profile.accountId),
      { data: profile },
      'GET',
      `/api/v1/people/${profile.accountId}`,
    ],
    [
      'GET /contests/{contestId}/teams',
      () => teams.listContestTeams(contest.id, { recruitingOnly: true }),
      page([]),
      'GET',
      `/api/v1/contests/${contest.id}/teams?recruitingOnly=true`,
    ],
    [
      'GET /teams',
      () => teams.listTeams({ contestId: contest.id, roleCode: 'design' }),
      page([]),
      'GET',
      `/api/v1/teams?contestId=${contest.id}&roleCode=design`,
    ],
    [
      'GET /teams/{teamId}',
      () => teams.getTeam(ID),
      { data: team },
      'GET',
      `/api/v1/teams/${ID}`,
    ],
    [
      'GET /me/teams',
      () => teams.listMyTeams(),
      page([]),
      'GET',
      '/api/v1/me/teams',
    ],
    [
      'PUT /teams/{teamId}/recruitment/closure',
      () => teams.closeRecruitment(ID, VERSION),
      { data: { team: toTeamSummary(team) } },
      'PUT',
      `/api/v1/teams/${ID}/recruitment/closure`,
      VERSION,
    ],
    [
      'GET /me/applications',
      () => applications.listMyApplications({ status: 'discarded' }),
      page([]),
      'GET',
      '/api/v1/me/applications?status=discarded',
    ],
    [
      'GET /applications/{applicationId}',
      () => applications.getApplication(application.id),
      { data: application },
      'GET',
      `/api/v1/applications/${application.id}`,
    ],
    [
      'PUT /applications/{applicationId}/review-start',
      () => applications.startApplicationReview(application.id, VERSION),
      { data: application },
      'PUT',
      `/api/v1/applications/${application.id}/review-start`,
      VERSION,
    ],
    [
      'PUT /applications/{applicationId}/rejection',
      () => applications.rejectApplication(application.id, VERSION),
      { data: application },
      'PUT',
      `/api/v1/applications/${application.id}/rejection`,
      VERSION,
    ],
    [
      'GET /teams/{teamId}/applicants',
      () => applications.listTeamApplicants(ID, { status: 'reviewing' }),
      page([]),
      'GET',
      `/api/v1/teams/${ID}/applicants?status=reviewing`,
    ],
    [
      'GET /me/notifications',
      () => notifications.listMyNotifications({ unreadOnly: true }),
      { ...page([]), unreadCount: 0 },
      'GET',
      '/api/v1/me/notifications?unreadOnly=true',
    ],
    [
      'GET /me/notifications/unread-count',
      () => notifications.getUnreadNotificationCount(),
      { data: { unreadCount: 2 } },
      'GET',
      '/api/v1/me/notifications/unread-count',
    ],
    [
      'PUT /me/notifications/read',
      () => notifications.readNotifications({ notificationIds: [ID] }),
      { data: { updatedIds: [ID], unreadCount: 0 } },
      'PUT',
      '/api/v1/me/notifications/read',
      { notificationIds: [ID] },
    ],
  ];

  it.each(cases)('%s', async (_, run, body, method, url, requestBody) => {
    const fetchMock = respond(body);
    await run();
    expect(call(fetchMock)).toEqual({ url, method, body: requestBody });
  });

  it('POST /auth/logout sends no body and accepts 204', async () => {
    const fetchMock = respond(null, 204);
    await expect(auth.logout()).resolves.toBeUndefined();
    expect(call(fetchMock)).toEqual({
      url: '/api/v1/auth/logout',
      method: 'POST',
      body: undefined,
    });
  });

  it('POST /teams distinguishes first creation (201) from a resend (200)', async () => {
    const body = {
      requestId: '11111111-1111-4111-8111-111111111111',
      contestId: contest.id,
      name: '예시 프로젝트 팀',
      introduction: '공모전에 함께 참여할 동료를 찾는 예시 팀입니다.',
      capacity: '4',
      roleCodes: ['planning'],
      recruitmentDeadline: { date: '2026-11-30', time: null, timeZone: null },
    };
    const first = respond({ data: team }, 201);
    await expect(teams.createTeam(body)).resolves.toMatchObject({
      created: true,
    });
    expect(call(first)).toEqual({ url: '/api/v1/teams', method: 'POST', body });
    respond({ data: team }, 200);
    await expect(teams.createTeam(body)).resolves.toMatchObject({
      created: false,
    });
  });
});

// [출처 2] 응답이 문서 필드와 다르면 화면에 넘기지 않음
describe('response schemas reject shapes outside the contract', () => {
  it('rejects oversized bounded profile fields before reading their elements', () => {
    const readFirst = vi.fn(() => null);
    const fields = Array<unknown>(1_000).fill(null);
    Object.defineProperty(fields, 0, { get: readFirst });

    const result = profiles.profileFields.fieldCodes.safeParse(fields);

    expect(result.success).toBe(false);
    expect(readFirst).not.toHaveBeenCalled();
    if (!result.success) {
      expect(result.error.issues).toEqual([
        expect.objectContaining({ code: 'too_big', maximum: 3 }),
      ]);
    }
  });

  it.each([
    ['missing key', { ...profile, version: undefined }],
    ['undeclared key', { ...profile, email: 'x@example.com' }],
    ['snake_case key', { ...profile, real_name: profile.realName }],
    ['BIGINT as JSON number', { ...profile, version: 1 }],
    ['null for a non-null field', { ...profile, realName: null }],
    [
      'experience body without provided state',
      { ...profile, experienceBody: '경험' },
    ],
  ])('Profile: %s', async (_, data) => {
    respond({ data });
    await expect(profiles.getMyProfile()).rejects.toThrow();
  });

  it('rejects a non-UTC timestamp and a page without pagination', async () => {
    respond({ data: { ...contest, startsAt: '2026-10-01T00:00:00+09:00' } });
    await expect(contests.getContest(contest.id)).rejects.toThrow();
    respond({ data: [] });
    await expect(contests.listContests()).rejects.toThrow();
  });

  it('enforces ParticipationCapacity combinations and the audience pairing rule', () => {
    expect(
      contests.ParticipationCapacity.safeParse({
        kind: 'range',
        minimumMembers: '5',
        maximumMembers: '2',
      }).success,
    ).toBe(false);
    expect(
      contests.ParticipationCapacity.safeParse({
        kind: 'unlimited',
        minimumMembers: '1',
        maximumMembers: '9',
      }).success,
    ).toBe(false);
    expect(
      contests.ContestDetail.safeParse({
        ...contest,
        audienceCodes: ['unknown', 'student'],
      }).success,
    ).toBe(false);
  });

  it('validates request bodies before sending (TeamCreate role count by capacity)', async () => {
    const fetchMock = respond({ data: team }, 201);
    await expect(
      teams.createTeam({
        requestId: ID,
        contestId: contest.id,
        name: '한 명 팀',
        introduction: '혼자 참가하는 팀을 만들어요.',
        capacity: '1',
        roleCodes: ['planning'],
        recruitmentDeadline: { date: '2026-11-30' },
      }),
    ).rejects.toThrow();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
