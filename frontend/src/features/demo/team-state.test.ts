import { describe, expect, it } from 'vitest';
import type { Application } from '@/features/applications/api';
import { getPublicProfile } from '@/features/demo/data';
import {
  createDemoRecords,
  demoIds,
  type DemoDatabase,
  type TeamRecord,
} from '@/features/demo/fixtures';
import { demoAcademicUnits } from '@/features/demo/labels';
import { lifecycleReferenceDatabase } from '@/features/demo/lifecycle-fixtures';
import {
  appendNotifications,
  transitionNotifications,
} from '@/features/demo/notification-state';
import {
  applicantVisibleProfile,
  applyToTeam,
  cancelTeamApplication,
  contestOf,
  createTeamIssue,
  isTeamMember,
  recruitmentIssue,
  recruitmentReopeningIssue,
  reopenTeamRecruitment,
  selectTeamApplicant,
  teamOf,
  teamRecruitmentDeadline,
  type NewTeamInput,
  type Transition,
} from '@/features/demo/team-state';
import { withProfile } from '@/test/render';

const { accounts: a, teams: t, applications: ap, contests: c } = demoIds;
const ME = a.me;

// 성공한 전이의 저장소. 실패하면 오류 코드를 보여 주며 테스트를 멈춥니다.
const ok = (transition: Transition): DemoDatabase => {
  if ('error' in transition) throw new Error(transition.error.code);
  return transition.db;
};
const codeOf = (transition: Transition) =>
  'error' in transition ? transition.error.code : null;
const state = () => createDemoRecords();
const publicState = () => withProfile(state(), ME, { isPublic: true });
const team = (db: DemoDatabase, teamId: string) => teamOf(db, teamId)!;
const applicationOf = (db: DemoDatabase, id: string) =>
  db.applications.find((item) => item.id === id);
const patchTeam = (
  db: DemoDatabase,
  teamId: string,
  patch: Partial<TeamRecord>,
): DemoDatabase => ({
  ...db,
  teams: db.teams.map((item) =>
    item.id === teamId ? { ...item, ...patch } : item,
  ),
});
// 같은 공모전에 팀장 한 명만 있는 다른 팀을 추가
const withTeam = (
  db: DemoDatabase,
  from: string,
  id: string,
  ownerAccountId: string,
): DemoDatabase => ({
  ...db,
  teams: [
    ...db.teams,
    { ...db.teams.find((item) => item.id === from)!, id, ownerAccountId },
  ],
  memberships: [
    ...db.memberships,
    {
      membershipId: `${id}-leader`,
      teamId: id,
      accountId: ownerAccountId,
      membershipRole: 'leader',
      roleCode: null,
      joinedAt: '2026-10-10T00:00:00Z',
      endedAt: null,
    },
  ],
});

describe('explicit recruitment reopening and parallel applications', () => {
  it('allows parallel applications to different teams of the same contest without consuming seats', () => {
    const before = withTeam(
      publicState(),
      t.makers,
      'other-campus-team',
      a.doyun,
    );
    const first = ok(
      applyToTeam(before, ME, t.makers, 'planning', null, 'first'),
    );
    const second = ok(
      applyToTeam(first, ME, 'other-campus-team', 'planning', null, 'second'),
    );
    expect(second.applications.slice(-2).map((item) => item.status)).toEqual([
      'submitted',
      'submitted',
    ]);
    expect(second.teams).toEqual(before.teams);
    expect(second.memberships).toEqual(before.memberships);
    expect(
      codeOf(applyToTeam(second, ME, t.makers, 'planning', null, 'duplicate')),
    ).toBe('DUPLICATE_APPLICATION');
  });

  it('only discards the selected person’s other pending applications for the same contest', () => {
    const base = withTeam(state(), t.greenwave, 'other-green-team', a.doyun);
    const applicant = applicationOf(base, ap.seoyeon)!;
    const other: Application = {
      ...applicant,
      id: 'other-pending',
      teamId: 'other-green-team',
      status: 'submitted',
    };
    const records: Application[] = [
      other,
      { ...other, id: 'other-reviewing', status: 'reviewing' },
      {
        ...other,
        id: 'other-contest',
        teamId: t.makers,
        contestId: c.campus,
      },
      ...(['canceled', 'rejected', 'discarded'] as const).map((status) => ({
        ...other,
        id: `history-${status}`,
        status,
      })),
      { ...other, id: 'another-person', applicantAccountId: a.sua },
    ];
    const before = {
      ...base,
      applications: [...base.applications, ...records],
    };
    const next = ok(selectTeamApplicant(before, applicant.id, ME, 'm-new'));
    for (const id of ['other-pending', 'other-reviewing'])
      expect(applicationOf(next, id)).toMatchObject({
        status: 'discarded',
        discardReason: 'selected_elsewhere',
        discardedByApplicationId: applicant.id,
      });
    for (const old of records.slice(2))
      expect(applicationOf(next, old.id)).toEqual(old);
    expect(
      codeOf(selectTeamApplicant(next, other.id, a.doyun, 'm-other')),
    ).toBe('INVALID_APPLICATION_STATE');
    const notifications = transitionNotifications(
      before,
      next,
      'selection-event',
      '2026-10-19T00:00:00Z',
    );
    expect(
      notifications.map((item) => [item.applicationId, item.eventStatus]),
    ).toEqual([
      [applicant.id, 'selected'],
      ['other-pending', 'discarded'],
      ['other-reviewing', 'discarded'],
    ]);
    expect(
      notifications.every(
        (item) => item.recipientAccountId === applicant.applicantAccountId,
      ),
    ).toBe(true);
    expect(appendNotifications(notifications, notifications)).toEqual(
      notifications,
    );
    expect(
      transitionNotifications(next, next, 'retry', '2026-10-19T00:00:01Z'),
    ).toEqual([]);
    const full = patchTeam(before, t.greenwave, { capacity: '2' });
    expect(codeOf(selectTeamApplicant(full, applicant.id, ME, 'm-full'))).toBe(
      'TEAM_FULL',
    );
    expect(applicationOf(before, other.id)?.status).toBe('submitted');
  });

  it('closes on the last selected seat and keeps it closed when that seat is returned', () => {
    const before = patchTeam(state(), t.greenwave, { capacity: '3' });
    const selected = ok(
      selectTeamApplicant(before, ap.seoyeon, ME, 'm-seoyeon'),
    );
    expect(team(selected, t.greenwave)).toMatchObject({
      recruitmentState: 'closed',
      closedReason: 'capacity_reached',
    });
    const canceled = ok(cancelTeamApplication(selected, ap.seoyeon, a.seoyeon));
    const returned = team(canceled, t.greenwave);
    expect(returned.memberCount).toBe(2);
    expect(returned.recruitmentState).toBe('closed');
    expect(recruitmentIssue(returned)).toMatch(/모집이 마감/);
    expect(
      codeOf(reopenTeamRecruitment(canceled, t.greenwave, a.seoyeon)),
    ).toBe('FORBIDDEN');
    const reopened = ok(reopenTeamRecruitment(canceled, t.greenwave, ME));
    expect(recruitmentIssue(team(reopened, t.greenwave))).toBeNull();
    expect(reopened.applications).toEqual(canceled.applications);
  });

  it('keeps discarded history unchanged after selected cancellation and explicit reopening', () => {
    const before = lifecycleReferenceDatabase();
    const discarded = (db: DemoDatabase) =>
      db.applications.filter((item) => item.status === 'discarded');
    const canceled = ok(cancelTeamApplication(before, ap.localcrew, ME));
    expect(discarded(canceled)).toEqual(discarded(before));
    const reopened = ok(reopenTeamRecruitment(canceled, t.greenwave, ME));
    expect(reopened.applications).toEqual(canceled.applications);
    expect(codeOf(reopenTeamRecruitment(reopened, t.greenwave, ME))).toBe(
      'INVALID_RECRUITMENT_STATE',
    );
  });

  // docs/api/teams.md#values: 모집 상태는 open|closed뿐이며, 정원 충족으로 마감된 팀은 팀원이 취소해도 마감 유지
  it('keeps a capacity-closed team closed when a member cancels', () => {
    const next = ok(cancelTeamApplication(state(), ap.localcrew, ME));
    expect(team(next, t.localcrew)).toMatchObject({
      recruitmentState: 'closed',
      closedReason: 'capacity_reached',
    });
  });

  it('checks authority, seats and exact time boundaries when reopening', () => {
    const db = state();
    const closed = {
      ...team(db, t.greenwave),
      recruitmentState: 'closed' as const,
      recruitmentEndsAt: '2026-10-18T15:00:00Z',
    };
    const cutoff = Date.parse('2026-10-18T15:00:00Z');
    expect(recruitmentReopeningIssue(closed, ME, cutoff - 1)).toBeNull();
    expect(recruitmentReopeningIssue(closed, ME, cutoff)).toMatch(/기한/);
    expect(
      recruitmentReopeningIssue(
        { ...closed, ownerAccountId: a.doyun },
        ME,
        cutoff - 1,
      ),
    ).toMatch(/팀장만/);
    expect(
      recruitmentReopeningIssue(
        { ...closed, memberCount: Number(closed.capacity) },
        ME,
        cutoff - 1,
      ),
    ).toMatch(/정원/);
    expect(
      recruitmentReopeningIssue(
        { ...closed, contest: contestOf(db, c.upcoming)! },
        ME,
      ),
    ).toMatch(/접수가 시작/);
    expect(
      recruitmentReopeningIssue(
        {
          ...closed,
          contest: contestOf(db, c.solo)!,
          capacity: '1',
          memberCount: 1,
        },
        ME,
      ),
    ).toMatch(/정원/);
    expect(
      recruitmentReopeningIssue(closed, ME, Date.parse('2026-12-01T00:00:00Z')),
    ).toMatch(/공모전 접수가 마감/);
  });
});

describe('team reference transitions', () => {
  it('confirms selection and consumes a seat in the same transition', () => {
    const before = state();
    const next = ok(selectTeamApplicant(before, ap.seoyeon, ME, 'm1'));
    expect(team(next, t.greenwave).memberCount).toBe(3);
    expect(isTeamMember(next, t.greenwave, a.seoyeon)).toBe(true);
    expect(applicationOf(next, ap.seoyeon)?.status).toBe('selected');
    expect(codeOf(selectTeamApplicant(next, ap.seoyeon, ME, 'm2'))).toBe(
      'INVALID_APPLICATION_STATE',
    );
    expect(team(before, t.greenwave).memberCount).toBe(2);
  });
  it('allows only one of two selections for the last seat', () => {
    const before = patchTeam(state(), t.greenwave, { capacity: '3' });
    const first = ok(selectTeamApplicant(before, ap.seoyeon, ME, 'm1'));
    expect(codeOf(selectTeamApplicant(first, ap.sua, ME, 'm2'))).toBe(
      'TEAM_FULL',
    );
    expect(team(first, t.greenwave).memberCount).toBe(3);
    expect(applicationOf(first, ap.sua)?.status).toBe('reviewing');
  });
  it('rejects a second confirmed membership for the same contest', () => {
    const before = withTeam(
      state(),
      t.greenwave,
      'other-green-team',
      a.seoyeon,
    );
    expect(codeOf(selectTeamApplicant(before, ap.seoyeon, ME, 'm1'))).toBe(
      'MEMBERSHIP_CONFLICT',
    );
  });
  it('cancels a selected application, revokes membership, and returns exactly one seat without reopening', () => {
    const before = state();
    const application = before.applications.find(
      (item) => item.status === 'selected',
    )!;
    const next = ok(cancelTeamApplication(before, application.id, ME));
    const oldTeam = team(before, application.teamId);
    const updated = team(next, application.teamId);
    expect(isTeamMember(next, application.teamId, ME)).toBe(false);
    expect(updated.memberCount).toBe(oldTeam.memberCount - 1);
    expect(updated.recruitmentState).toBe(oldTeam.recruitmentState);
    expect(applicationOf(next, application.id)?.status).toBe('canceled');
    expect(codeOf(cancelTeamApplication(next, application.id, ME))).toBe(
      'INVALID_APPLICATION_STATE',
    );
  });
  it('allows an unadvertised role, and reapplication gets a fresh identity', () => {
    const before = publicState();
    const first = ok(
      applyToTeam(before, ME, t.makers, 'marketing', null, 'new-1'),
    );
    expect(team(first, t.makers).memberCount).toBe(
      team(before, t.makers).memberCount,
    );
    const canceled = ok(cancelTeamApplication(first, 'new-1', ME));
    const second = ok(
      applyToTeam(canceled, ME, t.makers, 'planning', '다시 지원해요', 'new-2'),
    );
    expect(applicationOf(second, 'new-2')?.status).toBe('submitted');
    expect(codeOf(cancelTeamApplication(second, 'new-1', ME))).toBe(
      'INVALID_APPLICATION_STATE',
    );
    expect(codeOf(selectTeamApplicant(second, 'new-1', a.minjun, 'm1'))).toBe(
      'INVALID_APPLICATION_STATE',
    );
    expect(
      codeOf(applyToTeam(second, ME, t.makers, 'planning', null, 'new-3')),
    ).toBe('DUPLICATE_APPLICATION');
  });
  it('accepts applications while others are under review, but blocks deadline, full capacity, missing profile and long messages', () => {
    const base = publicState();
    const before: DemoDatabase = {
      ...base,
      applications: [
        ...base.applications,
        {
          ...applicationOf(base, ap.sua)!,
          id: 'sua-reviewing',
          teamId: t.makers,
          contestId: c.campus,
        },
      ],
    };
    const apply = (db: DemoDatabase, message: string | null, id: string) =>
      applyToTeam(db, ME, t.makers, 'planning', message, id);
    expect(codeOf(apply(before, null, 'review-new'))).toBeNull();
    expect(
      codeOf(
        apply(withProfile(before, ME, { fieldCodes: [] }), null, 'missing'),
      ),
    ).toBe('PROFILE_REQUIRED');
    expect(codeOf(apply(before, 'x'.repeat(1001), 'long'))).toBe(
      'VALIDATION_ERROR',
    );
    const members = String(team(before, t.makers).memberCount);
    expect(
      codeOf(
        apply(patchTeam(before, t.makers, { capacity: members }), null, 'full'),
      ),
    ).toBe('TEAM_FULL');
    const expired = patchTeam(before, t.makers, {
      capacity: '10',
      recruitmentEndsAt: '2026-10-17T15:00:00Z',
    });
    expect(codeOf(apply(expired, null, 'expired'))).toBe(
      'RECRUITMENT_DEADLINE_PASSED',
    );
  });
  it('validates the official target capacity without requiring all members at creation', () => {
    const db = state();
    const input: NewTeamInput = {
      name: '새로운 팀',
      introduction: '공모전 아이디어를 함께 구체화해요',
      contestId: c.campus,
      roleCodes: ['planning'],
      capacity: 4,
      recruitmentDeadline: { date: '2026-11-01' },
    };
    const message = (patch: Partial<NewTeamInput>) =>
      createTeamIssue({ ...input, ...patch }, db, ME)?.message;
    expect(createTeamIssue(input, db, ME)).toBeNull();
    expect(message({ capacity: 1 })).toMatch(/공식 참가 인원/);
    expect(message({ capacity: 100 })).toMatch(/공식 참가 인원/);
    expect(message({ recruitmentDeadline: { date: '2026-12-01' } })).toMatch(
      /마감/,
    );
    expect(message({ contestId: c.green })).toMatch(/이미/);
  });
});

describe('applicant visibility', () => {
  const department = demoAcademicUnits.find(
    (unit) => unit.name === '소프트웨어학과',
  )!;
  const privateApplicant = {
    realName: '비공개 지원자',
    introduction: '지원자의 자기소개',
    experienceState: 'provided' as const,
    experienceBody: '지원자의 경험',
    academicStatusCode: 'enrolled',
    gradeCode: 'year_3',
    academicUnitId: department.id,
    skillCodes: ['programming', 'ui_ux'],
    fieldCodes: ['society_culture'],
    weeklyAvailabilityCode: 'from_5_to_10',
    isPublic: false,
    portfolio: { url: 'https://example.com/private', title: '비공개 링크' },
  };
  it('shares the full private profile in applicant review while excluding it from discovery', () => {
    const db = withProfile(state(), a.seoyeon, privateApplicant);
    const application = applicationOf(db, ap.seoyeon)!;
    const profile = applicantVisibleProfile(db, application)!;
    expect(getPublicProfile(profile)).toBeNull();
    expect(profile).toMatchObject(privateApplicant);
  });
  it('uses the current self profile instead of a stored application snapshot', () => {
    const current = {
      realName: '수정된 이름',
      introduction: '수정된 자기소개',
      isPublic: false,
      weeklyAvailabilityCode: 'from_10_to_20',
      portfolio: {
        url: 'https://example.com/current',
        title: '현재 포트폴리오',
      },
    };
    const db = withProfile(state(), ME, current);
    const application = {
      ...applicationOf(db, ap.localcrew)!,
      status: 'canceled' as const,
    };
    expect(applicantVisibleProfile(db, application)).toMatchObject(current);
    expect(
      applicantVisibleProfile(
        withProfile(db, ME, { isPublic: true }),
        application,
      ),
    ).toEqual({ ...applicantVisibleProfile(db, application), isPublic: true });
    expect(
      applicantVisibleProfile(
        withProfile(db, ME, { portfolio: null }),
        application,
      )?.portfolio,
    ).toBeNull();
  });
});

describe('normalized team policies', () => {
  const input: NewTeamInput = {
    name: '새 도전',
    introduction: '공모전을 함께 준비하고 완성해요.',
    contestId: c.campus,
    roleCodes: ['planning'],
    capacity: 3,
    recruitmentDeadline: { date: '2026-11-01' },
  };
  const message = (patch: Partial<NewTeamInput>) =>
    createTeamIssue({ ...input, ...patch }, state(), ME)?.message ?? null;
  it('requires a public profile only for a new application and allows unspecified academic fields', () => {
    expect(
      codeOf(applyToTeam(state(), ME, t.makers, 'planning', null, 'private')),
    ).toBe('PROFILE_PRIVATE');
    const next = ok(
      applyToTeam(
        withProfile(publicState(), ME, {
          academicStatusCode: null,
          gradeCode: null,
        }),
        ME,
        t.makers,
        'planning',
        null,
        'new',
      ),
    );
    expect(next.applications.at(-1)?.status).toBe('submitted');
    expect(codeOf(cancelTeamApplication(state(), ap.localcrew, ME))).toBeNull();
  });
  // docs/api/applications.md#application-create: 같은 공모전의 팀에 이미 소속되어 있으면 MEMBERSHIP_CONFLICT
  it('rejects a new application while the applicant already belongs to a team of the same contest', () => {
    const before = withTeam(publicState(), t.makers, 'same-contest-member', ME);
    expect(
      codeOf(applyToTeam(before, ME, t.makers, 'planning', null, 'new')),
    ).toBe('MEMBERSHIP_CONFLICT');
  });
  it('enforces name, introduction and role boundaries without treating whitespace as content', () => {
    expect(message({ name: ' 가 ' })).toMatch(/2~40/);
    expect(message({ introduction: ' '.repeat(12) })).toMatch(/10~/);
    expect(message({ name: '가'.repeat(41) })).toMatch(/2~40/);
    expect(message({ roleCodes: [] })).toMatch(/역할/);
    expect(message({ roleCodes: ['임의역할'] })).toMatch(/역할/);
    expect(message({ roleCodes: ['planning', 'planning'] })).toMatch(/역할/);
  });
  it('uses fixed official one-person capacity, omits roles and applies no arbitrary unlimited ceiling', () => {
    expect(
      message({ contestId: c.solo, capacity: 1, roleCodes: [] }),
    ).toBeNull();
    expect(message({ contestId: c.solo, capacity: 2 })).toMatch(
      /공식 참가 인원/,
    );
    expect(message({ contestId: c.solo, capacity: 1 })).toMatch(/1명/);
    expect(message({ contestId: c.openLab, capacity: 1000 })).toBeNull();
    expect(message({ capacity: NaN })).toMatch(/정원/);
    expect(message({ contestId: c.upcoming })).toMatch(/접수 중/);
  });
  it('closes at the exact team or contest boundary, whichever is earlier', () => {
    const db = state();
    const makers = {
      ...team(db, t.makers),
      recruitmentEndsAt: '2026-10-18T15:00:00Z',
    };
    const cutoff = Date.parse('2026-10-18T15:00:00Z');
    expect(recruitmentIssue(makers, cutoff - 1)).toBeNull();
    expect(recruitmentIssue(makers, cutoff)).toMatch(/기한/);
    const solo = {
      ...makers,
      contestId: c.solo,
      contest: contestOf(db, c.solo)!,
      recruitmentEndsAt: '2026-11-20T15:00:00Z',
    };
    expect(teamRecruitmentDeadline(solo)).toBe(
      Date.parse('2026-11-20T09:00:00Z'),
    );
    expect(contestOf(db, c.local)?.capacity.minimumMembers).toBe('2');
    expect(team(db, t.localcrew).memberCount).toBe(3);
  });
});
