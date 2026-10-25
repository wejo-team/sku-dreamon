/**
 * [참조 출처]
 * 1. docs/api/teams.md#deadline-input - 원문 날짜·시각·시간대로 UTC 마감 경계 계산, 잘못된 날짜·시간대 422
 * 2. docs/api/teams.md#transitions - 팀 생성 409 INVALID_CATALOG_SELECTION, 재전송은 정규화한 초기 입력으로 판별
 * 3. docs/api/teams.md#queries - 전체 팀 검색은 공모전명 포함, 특정 공모전의 팀은 제외
 * 4. docs/api/conventions.md#types, #errors - 경로 Id 형식 422, loc에 필드 이름, 오류 코드 표
 * 5. docs/api/applications.md#action-results - 이미 취소된 요청은 기존 취소 결과 유지
 * 6. docs/api/profiles.md#profile-fields, #portfolio - 앞뒤 공백 제거 후 길이, 제목 trim
 * 7. docs/api/catalogs.md#academic-unit - 학사 경로·선택 가능 여부 검증, 기존 비활성 소속 유지 허용
 * 8. docs/api/ai.md#request-lifecycle, #applicant-endpoints, #current-permissions - 재시도 수렴, 202 pending,
 *    진행 중 409, 같은 공모전 확정자 후보 제외, 팀장 관계 소멸 시 404
 * 9. docs/api/contests.md#contest-summary, #contest-timing - 코드 중복 금지, timing 경계 일치
 *
 * 검증에서 문서와 다르게 동작하던 항목(A1~A14)의 회귀 테스트입니다.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as ai from '@/features/ai/api';
import * as applications from '@/features/applications/api';
import * as auth from '@/features/auth/api';
import * as contests from '@/features/contests/api';
import * as notifications from '@/features/notifications/api';
import * as profiles from '@/features/profiles/api';
import * as teams from '@/features/teams/api';
import {
  createDemoRecords,
  deriveContest,
  demoIds,
  toContestSummary,
} from '@/features/demo/fixtures';
import { ApiError, withQuery } from '@/lib/api';
import { mockFetch, resetMockApi } from '@/lib/api-mock';
import { failAiRequestForMock } from '@/lib/api-mock/handlers-notifications-ai';
import { db } from '@/lib/api-mock/state';

const ids = demoIds;

beforeEach(() => {
  resetMockApi();
  vi.stubGlobal('fetch', (input: string, init: RequestInit) =>
    mockFetch(input, init),
  );
});

const failure = async (promise: Promise<unknown>) => {
  const error = await promise.then(
    () => null,
    (reason: unknown) => reason,
  );
  expect(error).toBeInstanceOf(ApiError);
  const apiError = error as ApiError;
  return {
    status: apiError.status,
    code: apiError.code,
    loc: apiError.issues?.[0]?.loc,
  };
};

const signIn = () =>
  auth.login({ loginId: 'dreamondemo', password: 'DreamonReview2026!' });

const raw = async (path: string, init: RequestInit = {}) => {
  const response = await mockFetch(`/api/v1${path}`, init);
  return { status: response.status, body: await response.json() };
};

const teamBody = (patch: Partial<teams.TeamCreate> = {}): teams.TeamCreate => ({
  requestId: crypto.randomUUID(),
  contestId: ids.contests.openLab,
  name: '열린 실험 팀',
  introduction: '열린 실험실에 함께 참가할 팀원을 찾아요.',
  capacity: '3',
  roleCodes: ['planning'],
  recruitmentDeadline: { date: '2026-11-20', time: null, timeZone: null },
  ...patch,
});

// 현재 프로필에서 편집 필드 13개만 골라 저장 본문을 만듭니다.
const writeOf = (
  profile: profiles.Profile,
  patch: Partial<profiles.ProfileWrite> = {},
): profiles.ProfileWrite => ({
  ...(Object.fromEntries(
    Object.keys(profiles.profileFields).map((key) => [
      key,
      profile[key as keyof profiles.Profile],
    ]),
  ) as Omit<profiles.ProfileWrite, 'expectedVersion'>),
  expectedVersion: profile.version,
  ...patch,
});

describe('team creation follows the deadline and catalog contract', () => {
  it('A1: uses the submitted time and time zone for the UTC boundary', async () => {
    await signIn();
    const { team } = await teams.createTeam(
      teamBody({
        recruitmentDeadline: {
          date: '2026-11-20',
          time: '18:00',
          timeZone: 'Asia/Seoul',
        },
      }),
    );
    expect(team.recruitmentEndsAt).toBe('2026-11-20T09:00:00Z');
    expect(team.recruitmentDeadline).toMatchObject({
      sourceTime: '18:00',
      sourceTimeZone: 'Asia/Seoul',
      timeDefaulted: false,
      timeZoneDefaulted: false,
    });
  });

  it('A2: rejects an unselectable role with 409 INVALID_CATALOG_SELECTION', async () => {
    await signIn();
    expect(
      await failure(
        teams.createTeam(teamBody({ roleCodes: ['unknown_role'] })),
      ),
    ).toMatchObject({ status: 409, code: 'INVALID_CATALOG_SELECTION' });
  });

  it('A3: accepts only real dates and IANA zones or UTC offsets', () => {
    const deadline = (value: object) =>
      teams.DeadlineInput.safeParse({ date: '2026-11-20', ...value }).success;
    expect(deadline({ date: '2026-02-30' })).toBe(false);
    expect(deadline({ date: '2028-02-29' })).toBe(true);
    expect(deadline({ timeZone: 'Mars/Phobos' })).toBe(false);
    expect(deadline({ timeZone: 'Seoul' })).toBe(false);
    expect(deadline({ timeZone: '+09:00' })).toBe(true);
    expect(deadline({ timeZone: 'Asia/Seoul' })).toBe(true);
  });

  it('A5: names the request field in a business-rule 422', async () => {
    await signIn();
    expect(
      await failure(teams.createTeam(teamBody({ name: ' 가 ' }))),
    ).toMatchObject({ status: 422, loc: ['body', 'name'] });
  });

  it('A7: treats a resend with the same normalized input as the same attempt', async () => {
    await signIn();
    const body = teamBody();
    const first = await teams.createTeam(body);
    const resend = await teams.createTeam({ ...body, name: ` ${body.name} ` });
    expect(resend).toMatchObject({
      created: false,
      team: { id: first.team.id },
    });
  });
});

describe('common mock contract', () => {
  it('A4: rejects a malformed path ID with 422 and its location', async () => {
    expect(await failure(teams.getTeam('not-a-uuid'))).toMatchObject({
      status: 422,
      loc: ['path', 'teamId'],
    });
  });

  it('A5: names the query field when a single query value is invalid', async () => {
    const { status, body } = await raw('/contests?registrationStatus=bogus');
    expect(status).toBe(422);
    expect(body.detail[0].loc).toEqual(['query', 'registrationStatus']);
  });

  it('A13: answers an undefined method and path combination with a documented code', async () => {
    const { status, body } = await raw(`/teams/${ids.teams.makers}`, {
      method: 'DELETE',
    });
    expect(status).toBe(404);
    expect(body.error.code).toBe('RESOURCE_NOT_FOUND');
  });

  it('A14: omits empty query values', () => {
    expect(withQuery('/contests', { fieldCode: '', q: 'x' })).toBe(
      '/contests?q=x',
    );
  });
});

describe('team list and cancellation results', () => {
  it('A6: searches contest titles across all teams, even with a contest filter', async () => {
    const campus = await contests.getContest(ids.contests.campus);
    const all = await teams.listTeams({
      contestId: ids.contests.campus,
      q: campus.title,
    });
    expect(all.data.map((team) => team.id)).toContain(ids.teams.makers);
    const scoped = await teams.listContestTeams(ids.contests.campus, {
      q: campus.title,
    });
    expect(scoped.pagination.total).toBe(0);
  });

  it('A8: keeps the original cancellation result on a repeated request', async () => {
    await signIn();
    const current = await applications.getApplication(
      ids.applications.localcrew,
    );
    const first = await applications.cancelApplication(current.id, {
      expectedVersion: current.version,
    });
    expect(first.membershipEnded).toBe(true);
    const again = await applications.cancelApplication(current.id, {
      expectedVersion: first.application.version,
    });
    expect(again).toEqual(first);
  });
});

describe('profile save normalization', () => {
  it('A9: checks trimmed lengths and stores a trimmed portfolio title', async () => {
    await signIn();
    const profile = await profiles.getMyProfile();
    const blank = await raw('/me/profile', {
      method: 'PUT',
      body: JSON.stringify(writeOf(profile, { realName: '   ' })),
    });
    expect(blank.status).toBe(422);
    expect(blank.body.detail[0].loc).toEqual(['body', 'realName']);
    const saved = await profiles.putMyProfile(
      writeOf(profile, {
        realName: '  김지우  ',
        portfolio: { url: 'https://example.com/work', title: '  작업집  ' },
      }),
    );
    expect(saved.portfolio).toEqual({
      url: 'https://example.com/work',
      title: '작업집',
    });
  });

  it('A9: rejects a new inactive academic unit but keeps an existing one', async () => {
    await signIn();
    const units = db().academicUnits;
    const major = units.find((unit) => unit.parentId !== null)!;
    const profile = await profiles.putMyProfile(
      writeOf(await profiles.getMyProfile(), { academicUnitId: major.id }),
    );
    // 선택 이후 비활성화된 소속은 다른 필드 수정 때 그대로 유지할 수 있음
    major.isSelectable = false;
    const kept = await profiles.putMyProfile(
      writeOf(profile, { introduction: '소개를 고쳤어요.' }),
    );
    expect(kept.academicUnitId).toBe(major.id);
    const other = units.find(
      (unit) => unit.parentId !== null && unit.id !== major.id,
    )!;
    other.isSelectable = false;
    expect(
      await failure(
        profiles.putMyProfile(writeOf(kept, { academicUnitId: other.id })),
      ),
    ).toMatchObject({ status: 409, code: 'INVALID_ACADEMIC_PATH' });
  });
});

describe('AI request lifecycle', () => {
  it('A10: converges overlapping retries of the same failed attempt', async () => {
    await signIn();
    const conversation = await ai.createConversation({});
    const { request } = await ai.sendMessage(conversation.id, {
      clientMessageId: crypto.randomUUID(),
      content: '디자인 팀 찾아줘',
    });
    failAiRequestForMock(request.id);
    const first = await ai.retryAiRequest(request.id, { expectedAttempt: 1 });
    const overlap = await ai.retryAiRequest(request.id, { expectedAttempt: 1 });
    expect(first.request).toMatchObject({ attempt: 2, status: 'pending' });
    expect(overlap.request).toEqual(first.request);
    failAiRequestForMock(request.id);
    await ai.retryAiRequest(request.id, { expectedAttempt: 2 });
    expect(
      await failure(ai.retryAiRequest(request.id, { expectedAttempt: 1 })),
    ).toMatchObject({ status: 409, code: 'ATTEMPT_CONFLICT' });
    expect((await ai.getAiRequest(request.id)).status).toBe('succeeded');
  });

  it('A11: accepts reviews as pending and rejects a second running request', async () => {
    await signIn();
    const accepted = await ai.requestApplicantReview(ids.applications.seoyeon);
    expect(accepted.request.status).toBe('pending');
    expect(
      await failure(ai.requestApplicantReview(ids.applications.seoyeon)),
    ).toMatchObject({ status: 409, code: 'REQUEST_ALREADY_RUNNING' });
    const done = await ai.getApplicantReview(ids.applications.seoyeon);
    expect(done.status).toBe('succeeded');
    await ai.requestApplicantRecommendations(ids.teams.greenwave);
    expect(
      await failure(ai.requestApplicantRecommendations(ids.teams.greenwave)),
    ).toMatchObject({ status: 409, code: 'REQUEST_ALREADY_RUNNING' });
  });

  it('A11: excludes applicants confirmed in the same contest and hides results after leadership changes', async () => {
    await signIn();
    // 김서연이 같은 공모전의 다른 팀에 확정 소속된 상태
    const otherTeamId = crypto.randomUUID();
    const greenwave = db().teams.find(
      (team) => team.id === ids.teams.greenwave,
    )!;
    db().teams.push({
      ...greenwave,
      id: otherTeamId,
      ownerAccountId: ids.accounts.seoyeon,
    });
    db().memberships.push({
      membershipId: crypto.randomUUID(),
      teamId: otherTeamId,
      accountId: ids.accounts.seoyeon,
      membershipRole: 'leader',
      roleCode: null,
      joinedAt: '2026-10-17T00:00:00Z',
      endedAt: null,
    });
    const { request } = await ai.requestApplicantRecommendations(
      ids.teams.greenwave,
    );
    const done = await ai.getAiRequest(request.id);
    expect(
      done.result?.kind === 'applicant_recommendation' &&
        done.result.candidates.map((item) => item.applicationId),
    ).toEqual([ids.applications.sua]);
    greenwave.ownerAccountId = ids.accounts.doyun;
    expect(await failure(ai.getAiRequest(request.id))).toMatchObject({
      status: 404,
    });
  });
});

describe('A12: response schemas enforce documented combinations', () => {
  const records = createDemoRecords();
  const contest = deriveContest(records.contests[0]!, records);
  it('rejects duplicated field codes and mismatched timing boundaries', () => {
    const summary = toContestSummary(contest);
    expect(
      contests.ContestSummary.safeParse({
        ...summary,
        fieldCodes: ['it_tech', 'it_tech'],
      }).success,
    ).toBe(false);
    expect(
      contests.Contest.safeParse({
        ...contest,
        timing: { ...contest.timing, endsAt: '2030-01-01T00:00:00Z' },
      }).success,
    ).toBe(false);
    expect(contests.Contest.safeParse(contest).success).toBe(true);
  });
});

describe('endpoints without earlier coverage', () => {
  it('reads one notification, shows the conversation view and cancels a pending request', async () => {
    await signIn();
    const notification = await notifications.readNotification(
      ids.notifications.seoyeonApplied,
    );
    expect(notification.readAt).not.toBeNull();
    const conversation = await ai.createConversation({});
    const { request } = await ai.sendMessage(conversation.id, {
      clientMessageId: crypto.randomUUID(),
      content: '디자인 팀 찾아줘',
    });
    const canceled = await ai.cancelAiRequest(request.id, {
      expectedAttempt: 1,
    });
    expect(canceled.status).toBe('canceled');
    const view = await ai.getConversation(conversation.id);
    expect(view.messages.map((item) => item.role)).toEqual(['user']);
    expect(view.requests.map((item) => item.status)).toEqual(['canceled']);
  });
});
