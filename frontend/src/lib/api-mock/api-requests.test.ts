/**
 * [참조 출처]
 * 1. docs/api/README.md - 영역별 문서의 메서드·경로·요청·응답을 프론트와 서버가 같이 검토
 * 2. docs/api/auth.md, catalogs.md, contests.md, profiles.md, teams.md, applications.md, notifications.md
 *    - 각 엔드포인트의 메서드·경로·query·요청 본문·성공 상태 코드
 * 3. docs/api/conventions.md#success-responses - 200·201·204 구분
 * 5. docs/api/conventions.md#csrf-transport - 상태 변경 요청에 X-CSRF-Token, 토큰은 GET /auth/csrf로 발급
 * 4. docs/development/testing.md - 「의미 있는 테스트」 API 계약은 실제 요청·응답으로 검사
 *
 * 영역별 API 함수(AI 제외, docs/api/ai.md 미구현)를 하나의 목업 세션에서 실제 사용 순서대로 호출하고,
 * 각 함수가 fetch로 내보낸 메서드·URL·JSON 본문과 응답 상태를 기록해 문서 값과 비교합니다.
 */

import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import * as applications from '@/features/applications/api';
import * as auth from '@/features/auth/api';
import * as catalogs from '@/features/catalogs/api';
import * as contests from '@/features/contests/api';
import * as notifications from '@/features/notifications/api';
import * as profiles from '@/features/profiles/api';
import * as teams from '@/features/teams/api';
import { demoIds } from '@/features/demo/fixtures';
import { mockFetch, resetMockApi } from '@/lib/api-mock';

const ids = demoIds;
type Sent = {
  method: string;
  url: string;
  body: unknown;
  status: number;
  csrf: boolean;
};
const sent: Sent[] = [];

beforeAll(() => resetMockApi({ signedIn: false }));

// 테스트 설정이 매 테스트 후 전역 stub을 되돌리므로 매번 다시 겁니다.
beforeEach(() => {
  // fetch를 감싸 실제로 나간 요청과 받은 상태 코드를 기록한 뒤 목업 서버로 보냅니다.
  vi.stubGlobal('fetch', async (url: string, init: RequestInit = {}) => {
    const response = await mockFetch(url, init);
    sent.push({
      method: init.method ?? 'GET',
      url,
      body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
      status: response.status,
      csrf: new Headers(init.headers).has('X-CSRF-Token'),
    });
    return response;
  });
});

// 앞 단계 응답에서 받은 값(버전·생성 ID)을 다음 요청에 사용합니다.
const saved: {
  profile?: profiles.Profile;
  teamId?: string;
  applicationId?: string;
  applicationVersion?: string;
  seoyeonVersion?: string;
  suaVersion?: string;
  notificationIds?: string[];
} = {};

const REQUEST_ID = '11111111-1111-4111-8111-111111111111';
const APPLICATION_REQUEST_ID = '22222222-2222-4222-8222-222222222222';
const PASSWORD = 'abcdefg!';
const DEMO_PASSWORD = 'DreamonReview2026!';

type Case = {
  name: string;
  run: () => Promise<unknown>;
  expected: () => { method: string; url: string; body?: unknown };
  status: number;
};

const teamCreate = (): teams.TeamCreate => ({
  requestId: REQUEST_ID,
  contestId: ids.contests.openLab,
  name: '열린 실험 팀',
  introduction: '열린 실험실에 함께 참가할 팀원을 찾아요.',
  capacity: '3',
  roleCodes: ['planning', 'development'],
  recruitmentDeadline: {
    date: '2026-11-20',
    time: '18:00',
    timeZone: 'Asia/Seoul',
  },
});

const profileWrite = (): profiles.ProfileWrite => {
  const current = saved.profile!;
  return {
    expectedVersion: current.version,
    realName: current.realName,
    profileImageCode: 'arti',
    academicStatusCode: 'enrolled',
    gradeCode: 'year_3',
    weeklyAvailabilityCode: 'from_5_to_10',
    academicUnitId: null,
    experienceState: 'provided',
    experienceBody: '교내 프로젝트에서 기획을 맡았어요.',
    introduction: current.introduction,
    fieldCodes: current.fieldCodes,
    roleCodes: current.roleCodes,
    skillCodes: ['service_planning'],
    portfolio: { url: 'https://example.com/work', title: '작업집' },
  };
};

const v1 = '/api/v1';
const cases: Case[] = [
  // ─── auth ───
  {
    name: 'GET /auth/csrf',
    run: () => auth.getCsrfToken(),
    expected: () => ({ method: 'GET', url: `${v1}/auth/csrf` }),
    status: 200,
  },
  {
    name: 'GET /auth/login-id-availability',
    run: () => auth.getLoginIdAvailability('NewMember01'),
    expected: () => ({
      method: 'GET',
      url: `${v1}/auth/login-id-availability?loginId=NewMember01`,
    }),
    status: 200,
  },
  {
    name: 'POST /accounts',
    run: () =>
      auth.createAccount({ loginId: 'newmember01', password: PASSWORD }),
    expected: () => ({
      method: 'POST',
      url: `${v1}/accounts`,
      body: { loginId: 'newmember01', password: PASSWORD },
    }),
    status: 201,
  },
  {
    name: 'POST /auth/logout',
    run: () => auth.logout(),
    expected: () => ({ method: 'POST', url: `${v1}/auth/logout` }),
    status: 204,
  },
  {
    name: 'POST /auth/login',
    run: () => auth.login({ loginId: 'dreamondemo', password: DEMO_PASSWORD }),
    expected: () => ({
      method: 'POST',
      url: `${v1}/auth/login`,
      body: { loginId: 'dreamondemo', password: DEMO_PASSWORD },
    }),
    status: 200,
  },
  {
    name: 'GET /me',
    run: () => auth.getMe(),
    expected: () => ({ method: 'GET', url: `${v1}/me` }),
    status: 200,
  },
  // ─── catalogs ───
  {
    name: 'GET /catalogs',
    run: () => catalogs.getCatalogs(),
    expected: () => ({ method: 'GET', url: `${v1}/catalogs` }),
    status: 200,
  },
  {
    name: 'GET /catalogs/academic-units',
    run: () => catalogs.getAcademicUnits(),
    expected: () => ({ method: 'GET', url: `${v1}/catalogs/academic-units` }),
    status: 200,
  },
  // ─── contests ───
  {
    name: 'GET /contests',
    run: () =>
      contests.listContests({
        q: '캠퍼스',
        fieldCode: 'education',
        sort: 'deadline_asc',
        registrationStatus: 'open',
        page: 1,
        pageSize: 6,
      }),
    expected: () => ({
      method: 'GET',
      url: `${v1}/contests?q=${encodeURIComponent('캠퍼스')}&fieldCode=education&sort=deadline_asc&registrationStatus=open&page=1&pageSize=6`,
    }),
    status: 200,
  },
  {
    name: 'GET /contests/{contestId}',
    run: () => contests.getContest(ids.contests.campus),
    expected: () => ({
      method: 'GET',
      url: `${v1}/contests/${ids.contests.campus}`,
    }),
    status: 200,
  },
  // ─── profiles ───
  {
    name: 'GET /me/profile',
    run: async () => (saved.profile = await profiles.getMyProfile()),
    expected: () => ({ method: 'GET', url: `${v1}/me/profile` }),
    status: 200,
  },
  {
    name: 'PUT /me/profile',
    run: async () =>
      (saved.profile = await profiles.putMyProfile(profileWrite())),
    expected: () => ({
      method: 'PUT',
      url: `${v1}/me/profile`,
      body: { ...profileWrite(), expectedVersion: '1' },
    }),
    status: 200,
  },
  {
    name: 'PUT /me/profile/visibility',
    run: async () =>
      (saved.profile = await profiles.putMyProfileVisibility({
        expectedVersion: '2',
        isPublic: true,
      })),
    expected: () => ({
      method: 'PUT',
      url: `${v1}/me/profile/visibility`,
      body: { expectedVersion: '2', isPublic: true },
    }),
    status: 200,
  },
  {
    name: 'GET /people',
    run: () =>
      profiles.listPeople({
        q: '김서연',
        fieldCode: 'it_technology',
        roleCode: 'development',
        page: 1,
        pageSize: 10,
      }),
    expected: () => ({
      method: 'GET',
      url: `${v1}/people?q=${encodeURIComponent('김서연')}&fieldCode=it_technology&roleCode=development&page=1&pageSize=10`,
    }),
    status: 200,
  },
  {
    name: 'GET /people/{accountId}',
    run: () => profiles.getPerson(ids.accounts.seoyeon),
    expected: () => ({
      method: 'GET',
      url: `${v1}/people/${ids.accounts.seoyeon}`,
    }),
    status: 200,
  },
  // ─── teams ───
  {
    name: 'GET /contests/{contestId}/teams',
    run: () =>
      teams.listContestTeams(ids.contests.campus, {
        q: '메이커스',
        roleCode: 'planning',
        recruitingOnly: true,
        page: 1,
        pageSize: 5,
      }),
    expected: () => ({
      method: 'GET',
      url: `${v1}/contests/${ids.contests.campus}/teams?q=${encodeURIComponent('메이커스')}&roleCode=planning&recruitingOnly=true&page=1&pageSize=5`,
    }),
    status: 200,
  },
  {
    name: 'GET /teams',
    run: () =>
      teams.listTeams({ contestId: ids.contests.green, roleCode: 'design' }),
    expected: () => ({
      method: 'GET',
      url: `${v1}/teams?contestId=${ids.contests.green}&roleCode=design`,
    }),
    status: 200,
  },
  {
    name: 'GET /teams/{teamId}',
    run: () => teams.getTeam(ids.teams.makers),
    expected: () => ({ method: 'GET', url: `${v1}/teams/${ids.teams.makers}` }),
    status: 200,
  },
  {
    name: 'POST /teams',
    run: async () =>
      (saved.teamId = (await teams.createTeam(teamCreate())).team.id),
    expected: () => ({
      method: 'POST',
      url: `${v1}/teams`,
      body: teamCreate(),
    }),
    status: 201,
  },
  {
    name: 'GET /me/teams',
    run: () => teams.listMyTeams({ page: 1, pageSize: 20 }),
    expected: () => ({
      method: 'GET',
      url: `${v1}/me/teams?page=1&pageSize=20`,
    }),
    status: 200,
  },
  {
    name: 'GET /teams/{teamId}/space',
    run: () => teams.getTeamSpace(ids.teams.greenwave),
    expected: () => ({
      method: 'GET',
      url: `${v1}/teams/${ids.teams.greenwave}/space`,
    }),
    status: 200,
  },
  {
    name: 'PUT /teams/{teamId}/recruitment/closure',
    run: () =>
      teams.closeRecruitment(ids.teams.greenwave, { expectedVersion: '1' }),
    expected: () => ({
      method: 'PUT',
      url: `${v1}/teams/${ids.teams.greenwave}/recruitment/closure`,
      body: { expectedVersion: '1' },
    }),
    status: 200,
  },
  {
    name: 'PUT /teams/{teamId}/recruitment/reopening',
    run: () =>
      teams.reopenRecruitment(ids.teams.greenwave, { expectedVersion: '2' }),
    expected: () => ({
      method: 'PUT',
      url: `${v1}/teams/${ids.teams.greenwave}/recruitment/reopening`,
      body: { expectedVersion: '2' },
    }),
    status: 200,
  },
  // ─── applications ───
  {
    name: 'POST /teams/{teamId}/applications',
    run: async () => {
      const created = await applications.createApplication(ids.teams.makers, {
        requestId: APPLICATION_REQUEST_ID,
        roleCode: 'planning',
        message: '캠퍼스 문제를 함께 풀고 싶어요.',
      });
      saved.applicationId = created.application.id;
      saved.applicationVersion = created.application.version;
    },
    expected: () => ({
      method: 'POST',
      url: `${v1}/teams/${ids.teams.makers}/applications`,
      body: {
        requestId: APPLICATION_REQUEST_ID,
        roleCode: 'planning',
        message: '캠퍼스 문제를 함께 풀고 싶어요.',
      },
    }),
    status: 201,
  },
  {
    name: 'GET /me/applications',
    run: () =>
      applications.listMyApplications({ status: 'submitted', page: 1 }),
    expected: () => ({
      method: 'GET',
      url: `${v1}/me/applications?status=submitted&page=1`,
    }),
    status: 200,
  },
  {
    name: 'GET /applications/{applicationId}',
    run: () => applications.getApplication(saved.applicationId!),
    expected: () => ({
      method: 'GET',
      url: `${v1}/applications/${saved.applicationId}`,
    }),
    status: 200,
  },
  {
    name: 'PUT /applications/{applicationId}/cancellation',
    run: () =>
      applications.cancelApplication(saved.applicationId!, {
        expectedVersion: saved.applicationVersion!,
      }),
    expected: () => ({
      method: 'PUT',
      url: `${v1}/applications/${saved.applicationId}/cancellation`,
      body: { expectedVersion: '1' },
    }),
    status: 200,
  },
  {
    name: 'GET /teams/{teamId}/applicants',
    run: async () => {
      const list = await applications.listTeamApplicants(ids.teams.greenwave, {
        status: 'reviewing',
      });
      const version = (id: string) =>
        list.data.find((item) => item.application.id === id)!.application
          .version;
      saved.seoyeonVersion = version(ids.applications.seoyeon);
      saved.suaVersion = version(ids.applications.sua);
    },
    expected: () => ({
      method: 'GET',
      url: `${v1}/teams/${ids.teams.greenwave}/applicants?status=reviewing`,
    }),
    status: 200,
  },
  {
    name: 'GET /applications/{applicationId}/applicant',
    run: () => applications.getApplicant(ids.applications.seoyeon),
    expected: () => ({
      method: 'GET',
      url: `${v1}/applications/${ids.applications.seoyeon}/applicant`,
    }),
    status: 200,
  },
  {
    name: 'PUT /applications/{applicationId}/review-start',
    run: () =>
      applications.startApplicationReview(ids.applications.seoyeon, {
        expectedVersion: saved.seoyeonVersion!,
      }),
    expected: () => ({
      method: 'PUT',
      url: `${v1}/applications/${ids.applications.seoyeon}/review-start`,
      body: { expectedVersion: '2' },
    }),
    status: 200,
  },
  {
    name: 'PUT /applications/{applicationId}/selection',
    run: () =>
      applications.selectApplication(ids.applications.seoyeon, {
        expectedVersion: saved.seoyeonVersion!,
      }),
    expected: () => ({
      method: 'PUT',
      url: `${v1}/applications/${ids.applications.seoyeon}/selection`,
      body: { expectedVersion: '2' },
    }),
    status: 200,
  },
  {
    name: 'PUT /applications/{applicationId}/rejection',
    run: () =>
      applications.rejectApplication(ids.applications.sua, {
        expectedVersion: saved.suaVersion!,
      }),
    expected: () => ({
      method: 'PUT',
      url: `${v1}/applications/${ids.applications.sua}/rejection`,
      body: { expectedVersion: '2' },
    }),
    status: 200,
  },
  // ─── notifications ───
  {
    name: 'GET /me/notifications',
    run: async () => {
      const list = await notifications.listMyNotifications({
        unreadOnly: true,
        page: 1,
        pageSize: 10,
      });
      saved.notificationIds = list.data.map((item) => item.id);
    },
    expected: () => ({
      method: 'GET',
      url: `${v1}/me/notifications?unreadOnly=true&page=1&pageSize=10`,
    }),
    status: 200,
  },
  {
    name: 'GET /me/notifications/unread-count',
    run: () => notifications.getUnreadNotificationCount(),
    expected: () => ({
      method: 'GET',
      url: `${v1}/me/notifications/unread-count`,
    }),
    status: 200,
  },
  {
    name: 'PUT /me/notifications/{notificationId}/read',
    run: () => notifications.readNotification(saved.notificationIds![0]!),
    expected: () => ({
      method: 'PUT',
      url: `${v1}/me/notifications/${saved.notificationIds![0]}/read`,
    }),
    status: 200,
  },
  {
    name: 'PUT /me/notifications/read',
    run: () =>
      notifications.readNotifications({
        notificationIds: saved.notificationIds!,
      }),
    expected: () => ({
      method: 'PUT',
      url: `${v1}/me/notifications/read`,
      body: { notificationIds: saved.notificationIds },
    }),
    status: 200,
  },
];

describe('API functions send the documented method, path and body', () => {
  it('covers every documented endpoint exactly once', () => {
    expect(cases).toHaveLength(36);
    expect(new Set(cases.map((item) => item.name)).size).toBe(36);
  });

  // 같은 목업 세션에서 순서대로 실행합니다(앞 단계의 생성 ID·버전을 사용).
  it.each(cases)('$name', async ({ name, run, expected, status }) => {
    const before = sent.length;
    await run();
    // [출처 5] CSRF 토큰 조회(GET /auth/csrf)는 함수 요청과 따로 셉니다.
    const requests = sent
      .slice(before)
      .filter(
        (item) => name === 'GET /auth/csrf' || !item.url.endsWith('/auth/csrf'),
      );
    expect(requests).toHaveLength(1);
    const { body, ...rest } = expected();
    const csrf = rest.method !== 'GET';
    expect(requests[0]).toEqual({ ...rest, body, status, csrf });
  });
});
