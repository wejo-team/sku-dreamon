/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/team-state.ts - 팀·지원 상태 전이 원본
 * 2. docs/api/teams.md#values, #transitions - RecruitmentState open|closed, isRecruiting 계산, 모집 종료·재개
 * 3. docs/api/applications.md#transitions - 지원·선발·취소 전이, 같은 공모전의 다른 대기 지원 폐기, 409 코드
 * 4. docs/api/applications.md#application-create - 신규 지원 조건(공개·필수 프로필·모집·중복·재지원·소속)
 * 5. docs/api/teams.md#team-create - 팀 생성 조건과 같은 공모전의 본인 대기 지원 폐기
 * 6. docs/specs/team-recruitment.md#recruitment-reopening - 정원 충족 후 자동 재개 없음, 팀장 확인 후 재개
 * 7. docs/specs/team-recruitment.md#membership-capacity - 팀장 포함 정원, 선발 즉시 확정·자리 차감, 취소 시 반환
 *
 * API DTO 형태의 목업 저장소(DemoDatabase)에 대한 순수 상태 전이입니다. 화면(DemoProvider)과 목업 서버가
 * 같은 규칙을 씁니다. 실패는 API와 같은 409 코드와 화면 문구를 함께 돌려줍니다.
 */

import type { Application } from '@/features/applications/api';
import type { Contest } from '@/features/contests/api';
import type { Profile } from '@/features/profiles/api';
import type { DeadlineInput, Team, TeamMember } from '@/features/teams/api';
import {
  contestStatus,
  hasConfirmedMemberLimit,
  interpretDeadline,
  memberLimitLabel,
  referenceNow,
  capacityBounds,
} from '@/features/demo/contest-state';
import {
  currentMemberships,
  deriveContest,
  deriveTeam,
  toTeamMember,
  type DemoDatabase,
  type TeamRecord,
} from '@/features/demo/fixtures';
import { roleOptions } from '@/features/demo/labels';
import {
  missingProfileFields,
  profileTextLength,
} from '@/features/demo/profile-fields';

// field: 422 VALIDATION_ERROR일 때 loc에 넣을 요청 필드 이름(docs/api/conventions.md#errors)
export type TransitionError = { code: string; message: string; field?: string };
export type Transition = { db: DemoDatabase } | { error: TransitionError };
const failure = (code: string, message: string): Transition => ({
  error: { code, message },
});

export const PENDING_STATUSES: Application['status'][] = [
  'submitted',
  'reviewing',
];
export const isPending = (application: Pick<Application, 'status'>) =>
  PENDING_STATUSES.includes(application.status);

// Reference fixtures intentionally use a fixed date so archived designs stay reviewable.
export const referenceDate = '2026-10-18';

// ─── 조회 ──────────────────────────────────────────────────

export const contestOf = (db: DemoDatabase, contestId: string) => {
  const seed = db.contests.find((item) => item.id === contestId);
  return seed ? deriveContest(seed, db) : undefined;
};
export const allContests = (db: DemoDatabase): Contest[] =>
  db.contests.map((seed) => deriveContest(seed, db));

export const teamOf = (db: DemoDatabase, teamId: string): Team | undefined => {
  const record = db.teams.find((item) => item.id === teamId);
  return record ? deriveTeam(record, db) : undefined;
};
export const allTeams = (db: DemoDatabase): Team[] =>
  db.teams.map((record) => deriveTeam(record, db));

export const profileOf = (db: DemoDatabase, accountId: string) =>
  db.profiles.find((item) => item.accountId === accountId);

// [출처 7] 현재 팀장·확정 팀원
export const isTeamMember = (
  db: DemoDatabase,
  teamId: string,
  accountId: string,
) =>
  currentMemberships(db.memberships, teamId).some(
    (item) => item.accountId === accountId,
  );

export const isTeamOwner = (
  team: Pick<Team, 'ownerAccountId'>,
  accountId: string,
) => team.ownerAccountId === accountId;

// [출처 4] 같은 공모전의 현재 확정 소속
export const hasMembershipInContest = (
  db: DemoDatabase,
  contestId: string,
  accountId: string,
) =>
  db.memberships.some(
    (item) =>
      !item.endedAt &&
      item.accountId === accountId &&
      db.teams.find((team) => team.id === item.teamId)?.contestId === contestId,
  );

// 지원받은 팀장인지(지원자 프로필 열람 예외)
const receivedApplicationFrom = (
  db: DemoDatabase,
  ownerId: string,
  applicantId: string,
) =>
  db.applications.some(
    (item) =>
      item.applicantAccountId === applicantId &&
      db.teams.find((team) => team.id === item.teamId)?.ownerAccountId ===
        ownerId,
  );

// 소속 표시. 프로필은 본인·공개·지원받은 팀장 권한에서만
export function teamMembers(
  db: DemoDatabase,
  teamId: string,
  viewerId: string,
): TeamMember[] {
  return currentMemberships(db.memberships, teamId).map((membership) =>
    toTeamMember(
      membership,
      db.profiles,
      (profile) =>
        profile.accountId === viewerId ||
        profile.isPublic ||
        receivedApplicationFrom(db, viewerId, profile.accountId),
    ),
  );
}

// [출처 2] 팀 모집 마감 경계: 팀 기한과 공고 마감 중 이른 쪽
export const teamRecruitmentDeadline = (
  team: Pick<Team, 'recruitmentEndsAt' | 'contest'>,
) =>
  Math.min(Date.parse(team.recruitmentEndsAt), Date.parse(team.contest.endsAt));

// [출처 2, 4] 신규 접수가 막힌 이유(없으면 null)
export function recruitmentIssue(
  team: Team,
  now = referenceNow,
): string | null {
  const status = contestStatus(team.contest, now);
  if (status === 'closed') return '공모전 접수가 마감되어 지원할 수 없어요.';
  if (status === 'scheduled') return '공모전 접수가 시작되면 지원할 수 있어요.';
  if (team.recruitmentState === 'closed')
    return '모집이 마감되어 지금은 지원할 수 없어요.';
  if (now >= teamRecruitmentDeadline(team))
    return '팀 모집 기한이 지나 지원할 수 없어요.';
  if (team.memberCount >= Number(team.capacity))
    return '팀 정원이 모두 찼어요.';
  return null;
}

const recruitmentIssueCode = (team: Team, now: number) => {
  const status = contestStatus(team.contest, now);
  if (status !== 'open') return 'CONTEST_NOT_OPEN';
  if (team.recruitmentState === 'closed') return 'RECRUITMENT_CLOSED';
  if (now >= teamRecruitmentDeadline(team))
    return 'RECRUITMENT_DEADLINE_PASSED';
  return 'TEAM_FULL';
};

// [출처 6] 재개 불가 사유(없으면 null)
export function recruitmentReopeningIssue(
  team: Team,
  accountId: string,
  now = referenceNow,
) {
  if (!isTeamOwner(team, accountId))
    return '팀장만 모집을 다시 시작할 수 있어요.';
  if (team.recruitmentState !== 'closed')
    return '마감된 모집만 다시 시작할 수 있어요.';
  if (team.memberCount >= Number(team.capacity))
    return '팀 정원이 모두 차서 다시 모집할 수 없어요.';
  const status = contestStatus(team.contest, now);
  if (status === 'closed')
    return '공모전 접수가 마감되어 다시 모집할 수 없어요.';
  if (status === 'scheduled')
    return '공모전 접수가 시작되면 다시 모집할 수 있어요.';
  if (now >= teamRecruitmentDeadline(team))
    return '팀 모집 기한이 지나 다시 모집할 수 없어요.';
  return null;
}

// [출처 2] 모집 상태 문구. 색과 함께 문구로 구분
export function teamStatusLabel(team: Team, now = referenceNow) {
  if (team.recruitmentState === 'closed') return '모집 마감';
  if (team.memberCount >= Number(team.capacity)) return '정원 충족';
  if (contestStatus(team.contest, now) === 'scheduled') return '모집 예정';
  if (recruitmentIssue(team, now)) return '모집 마감';
  return '모집 중';
}

// [출처 3] 선발 가능 여부: 정원이 남았고 공고 접수 기간 안
export function selectionScenario(
  team: Team,
  now = referenceNow,
): 'ready' | 'full' | 'not-modeled' {
  if (team.memberCount >= Number(team.capacity)) return 'full';
  return now >= Date.parse(team.contest.endsAt) ? 'not-modeled' : 'ready';
}

// ─── 전이 ──────────────────────────────────────────────────

const replaceApplication = (db: DemoDatabase, next: Application) =>
  db.applications.map((item) => (item.id === next.id ? next : item));

const bump = (version: string) => (BigInt(version) + 1n).toString();
const stamp = (now: number) =>
  new Date(now).toISOString().replace('.000Z', 'Z');

// [출처 3, 5] 같은 공모전에서 해당 계정의 다른 대기 지원 폐기
function discardPending(
  applications: Application[],
  accountId: string,
  contestId: string,
  except: string | null,
  reason: NonNullable<Application['discardReason']>,
  cause: { applicationId?: string; teamId?: string },
  now: number,
) {
  return applications.map((item) =>
    item.applicantAccountId === accountId &&
    item.contestId === contestId &&
    item.id !== except &&
    isPending(item)
      ? {
          ...item,
          status: 'discarded' as const,
          discardReason: reason,
          discardedByApplicationId: cause.applicationId ?? null,
          discardedByTeamId: cause.teamId ?? null,
          version: bump(item.version),
          updatedAt: stamp(now),
        }
      : item,
  );
}

// [출처 4] 신규 지원
export function applyToTeam(
  db: DemoDatabase,
  accountId: string,
  teamId: string,
  roleCode: string,
  message: string | null,
  id: string,
  now = referenceNow,
): Transition {
  const team = teamOf(db, teamId);
  if (!team) return failure('RESOURCE_NOT_FOUND', '팀을 찾을 수 없어요.');
  const profile = profileOf(db, accountId);
  if (!profile || missingProfileFields(profile).length)
    return failure('PROFILE_REQUIRED', '필수 프로필을 먼저 완성해 주세요.');
  if (!profile.isPublic)
    return failure('PROFILE_PRIVATE', '프로필을 공개해야 지원할 수 있어요.');
  if (!roleOptions.some((item) => item.code === roleCode))
    return failure(
      'INVALID_CATALOG_SELECTION',
      '지원 역할을 다시 선택해 주세요.',
    );
  if (message && profileTextLength(message.trim()) > 1000)
    return {
      error: {
        code: 'VALIDATION_ERROR',
        message: '팀에 전할 말은 1,000자까지 입력할 수 있어요.',
        field: 'message',
      },
    };
  const issue = recruitmentIssue(team, now);
  if (issue) return failure(recruitmentIssueCode(team, now), issue);
  if (hasMembershipInContest(db, team.contestId, accountId))
    return failure(
      'MEMBERSHIP_CONFLICT',
      '이미 이 공모전의 팀에 소속되어 있어요.',
    );
  const mine = db.applications.filter(
    (item) => item.teamId === teamId && item.applicantAccountId === accountId,
  );
  if (mine.some(isPending))
    return failure('DUPLICATE_APPLICATION', '이미 이 팀에 지원했어요.');
  if (mine.some((item) => item.status === 'rejected'))
    return failure(
      'REAPPLICATION_NOT_ALLOWED',
      '이 팀에는 다시 지원할 수 없어요.',
    );
  const createdAt = stamp(now);
  const application: Application = {
    id,
    version: '1',
    teamId,
    contestId: team.contestId,
    applicantAccountId: accountId,
    roleCode,
    message: message?.trim() || null,
    status: 'submitted',
    discardReason: null,
    discardedByApplicationId: null,
    discardedByTeamId: null,
    submittedAt: createdAt,
    updatedAt: createdAt,
  };
  return { db: { ...db, applications: [...db.applications, application] } };
}

// [출처 3, 7] 선발: 팀원 확정·자리 차감·다른 대기 지원 폐기, 정원 충족 시 마감
export function selectTeamApplicant(
  db: DemoDatabase,
  applicationId: string,
  ownerId: string,
  membershipId: string,
  now = referenceNow,
): Transition {
  const application = db.applications.find((item) => item.id === applicationId);
  const team = application && teamOf(db, application.teamId);
  if (!application || !team)
    return failure('RESOURCE_NOT_FOUND', '지원서를 찾을 수 없어요.');
  if (!isTeamOwner(team, ownerId))
    return failure('FORBIDDEN', '팀장만 선발할 수 있어요.');
  if (!isPending(application))
    return failure(
      'INVALID_APPLICATION_STATE',
      '선발할 수 없는 지원 상태예요.',
    );
  const scenario = selectionScenario(team, now);
  if (scenario === 'full')
    return failure('TEAM_FULL', '팀 정원이 모두 찼어요.');
  if (scenario === 'not-modeled')
    return failure(
      'CONTEST_NOT_OPEN',
      '공모전 접수가 마감되어 선발할 수 없어요.',
    );
  if (
    hasMembershipInContest(db, team.contestId, application.applicantAccountId)
  )
    return failure(
      'MEMBERSHIP_CONFLICT',
      '지원자가 이미 이 공모전의 팀에 소속되어 있어요.',
    );
  const updatedAt = stamp(now);
  const selected: Application = {
    ...application,
    status: 'selected',
    version: bump(application.version),
    updatedAt,
  };
  const applications = discardPending(
    replaceApplication(db, selected),
    application.applicantAccountId,
    team.contestId,
    application.id,
    'selected_elsewhere',
    { applicationId: application.id },
    now,
  );
  const memberships = [
    ...db.memberships,
    {
      membershipId,
      teamId: team.id,
      accountId: application.applicantAccountId,
      membershipRole: 'member' as const,
      roleCode: application.roleCode,
      joinedAt: updatedAt,
      endedAt: null,
    },
  ];
  const full = team.memberCount + 1 >= Number(team.capacity);
  const teams = db.teams.map((item) =>
    item.id === team.id && full && item.recruitmentState === 'open'
      ? {
          ...item,
          recruitmentState: 'closed' as const,
          closedReason: 'capacity_reached' as const,
          version: bump(item.version),
        }
      : item,
  );
  return { db: { ...db, applications, memberships, teams } };
}

// [출처 3] 팀장의 명시적 검토 시작. 팀 모집 상태·정원은 유지
export function startApplicantReview(
  db: DemoDatabase,
  applicationId: string,
  ownerId: string,
  now = referenceNow,
): Transition {
  const application = db.applications.find((item) => item.id === applicationId);
  const team = application && teamOf(db, application.teamId);
  if (!application || !team)
    return failure('RESOURCE_NOT_FOUND', '지원서를 찾을 수 없어요.');
  if (!isTeamOwner(team, ownerId))
    return failure('FORBIDDEN', '팀장만 검토를 시작할 수 있어요.');
  if (application.status !== 'submitted')
    return failure(
      'INVALID_APPLICATION_STATE',
      '검토를 시작할 수 없는 상태예요.',
    );
  return {
    db: {
      ...db,
      applications: replaceApplication(db, {
        ...application,
        status: 'reviewing',
        version: bump(application.version),
        updatedAt: stamp(now),
      }),
    },
  };
}

// [출처 3] 팀장의 미선발. 소속·정원은 유지
export function rejectTeamApplicant(
  db: DemoDatabase,
  applicationId: string,
  ownerId: string,
  now = referenceNow,
): Transition {
  const application = db.applications.find((item) => item.id === applicationId);
  const team = application && teamOf(db, application.teamId);
  if (!application || !team)
    return failure('RESOURCE_NOT_FOUND', '지원서를 찾을 수 없어요.');
  if (!isTeamOwner(team, ownerId))
    return failure('FORBIDDEN', '팀장만 미선발 처리할 수 있어요.');
  if (!isPending(application))
    return failure(
      'INVALID_APPLICATION_STATE',
      '미선발 처리할 수 없는 상태예요.',
    );
  return {
    db: {
      ...db,
      applications: replaceApplication(db, {
        ...application,
        status: 'rejected',
        version: bump(application.version),
        updatedAt: stamp(now),
      }),
    },
  };
}

// [출처 3, 7] 본인 취소: 선발 후 취소는 소속 종료·자리 반환, 자동 재개·폐기 복원 없음
export function cancelTeamApplication(
  db: DemoDatabase,
  applicationId: string,
  accountId: string,
  now = referenceNow,
): Transition {
  const application = db.applications.find((item) => item.id === applicationId);
  if (!application || application.applicantAccountId !== accountId)
    return failure('RESOURCE_NOT_FOUND', '지원서를 찾을 수 없어요.');
  if (!['submitted', 'reviewing', 'selected'].includes(application.status))
    return failure(
      'INVALID_APPLICATION_STATE',
      '취소할 수 없는 지원 상태예요.',
    );
  const updatedAt = stamp(now);
  const memberships =
    application.status === 'selected'
      ? db.memberships.map((item) =>
          item.teamId === application.teamId &&
          item.accountId === accountId &&
          !item.endedAt
            ? { ...item, endedAt: updatedAt }
            : item,
        )
      : db.memberships;
  return {
    db: {
      ...db,
      memberships,
      applications: replaceApplication(db, {
        ...application,
        status: 'canceled',
        version: bump(application.version),
        updatedAt,
      }),
    },
  };
}

// [출처 2] 팀장의 모집 종료. 기존 지원·소속 유지
export function closeTeamRecruitment(
  db: DemoDatabase,
  teamId: string,
  accountId: string,
): Transition {
  const record = db.teams.find((item) => item.id === teamId);
  if (!record) return failure('RESOURCE_NOT_FOUND', '팀을 찾을 수 없어요.');
  if (record.ownerAccountId !== accountId)
    return failure('FORBIDDEN', '팀장만 모집을 마감할 수 있어요.');
  if (record.recruitmentState === 'closed')
    return failure('INVALID_RECRUITMENT_STATE', '이미 모집이 마감되었어요.');
  return {
    db: {
      ...db,
      teams: db.teams.map((item) =>
        item.id === teamId
          ? {
              ...item,
              recruitmentState: 'closed' as const,
              closedReason: 'leader_closed' as const,
              version: bump(item.version),
            }
          : item,
      ),
    },
  };
}

// [출처 6] 팀장 확인 후 재개
export function reopenTeamRecruitment(
  db: DemoDatabase,
  teamId: string,
  accountId: string,
  now = referenceNow,
): Transition {
  const team = teamOf(db, teamId);
  if (!team) return failure('RESOURCE_NOT_FOUND', '팀을 찾을 수 없어요.');
  const issue = recruitmentReopeningIssue(team, accountId, now);
  if (issue) {
    const code = !isTeamOwner(team, accountId)
      ? 'FORBIDDEN'
      : team.recruitmentState !== 'closed'
        ? 'INVALID_RECRUITMENT_STATE'
        : team.memberCount >= Number(team.capacity)
          ? 'TEAM_FULL'
          : contestStatus(team.contest, now) !== 'open'
            ? 'CONTEST_NOT_OPEN'
            : 'RECRUITMENT_DEADLINE_PASSED';
    return failure(code, issue);
  }
  return {
    db: {
      ...db,
      teams: db.teams.map((item) =>
        item.id === teamId
          ? {
              ...item,
              recruitmentState: 'open' as const,
              closedReason: null,
              version: bump(item.version),
            }
          : item,
      ),
    },
  };
}

// 팀 만들기 화면의 입력(TeamCreate 전 단계). 정원은 화면에서 숫자로 다룹니다.
export type NewTeamInput = {
  contestId: string;
  name: string;
  introduction: string;
  capacity: number;
  roleCodes: string[];
  /** [출처 5] 원문 마감 입력. 화면은 날짜만, API 요청은 시각·시간대도 보낼 수 있음 */
  recruitmentDeadline: DeadlineInput;
};

// [출처 5] 팀 생성 조건(없으면 null)
export function createTeamIssue(
  input: NewTeamInput,
  db: DemoDatabase,
  accountId: string,
  now = referenceNow,
): TransitionError | null {
  const issue = (code: string, message: string, field?: string) =>
    field ? { code, message, field } : { code, message };
  const contest = contestOf(db, input.contestId);
  if (!contest || contestStatus(contest, now) !== 'open')
    return issue('CONTEST_NOT_OPEN', '접수 중인 공모전을 선택해 주세요.');
  if (hasMembershipInContest(db, contest.id, accountId))
    return issue(
      'MEMBERSHIP_CONFLICT',
      '이미 이 공모전의 팀에 소속되어 있어요. 내 팀에서 확인해 주세요.',
    );
  const nameLength = profileTextLength(input.name);
  if (nameLength < 2 || nameLength > 40)
    return issue(
      'VALIDATION_ERROR',
      '팀 이름을 2~40자로 입력해 주세요.',
      'name',
    );
  const summaryLength = profileTextLength(input.introduction);
  if (summaryLength < 10 || summaryLength > 1000)
    return issue(
      'VALIDATION_ERROR',
      '팀 소개와 목표를 10~1,000자로 입력해 주세요.',
      'introduction',
    );
  if (!Number.isInteger(input.capacity) || input.capacity < 1)
    return issue(
      'VALIDATION_ERROR',
      '팀장 포함 총 정원을 1명 이상 입력해 주세요.',
      'capacity',
    );
  if (!hasConfirmedMemberLimit(contest.capacity))
    return issue(
      'CAPACITY_OUT_OF_RANGE',
      '공식 참가 인원을 확인한 뒤 팀을 만들 수 있어요.',
    );
  const { min, max } = capacityBounds(contest.capacity);
  if (
    (min !== null && input.capacity < min) ||
    (max !== null && input.capacity > max)
  )
    return issue(
      'CAPACITY_OUT_OF_RANGE',
      `공식 참가 인원 ${memberLimitLabel(contest.capacity)}에 맞춰 총 정원을 입력해 주세요.`,
    );
  if (
    input.capacity >= 2 &&
    (input.roleCodes.length < 1 ||
      input.roleCodes.length > 6 ||
      new Set(input.roleCodes).size !== input.roleCodes.length)
  )
    return issue(
      'VALIDATION_ERROR',
      '모집할 역할을 1~6개 선택해 주세요.',
      'roleCodes',
    );
  if (input.capacity === 1 && input.roleCodes.length)
    return issue(
      'VALIDATION_ERROR',
      '1명인 팀은 모집할 역할을 선택하지 않아요.',
      'roleCodes',
    );
  // [출처 5] 형식은 맞지만 선택할 수 없는 역할 코드는 409 INVALID_CATALOG_SELECTION
  if (
    input.roleCodes.some(
      (code) => !roleOptions.some((item) => item.code === code),
    )
  )
    return issue(
      'INVALID_CATALOG_SELECTION',
      '모집할 역할을 목록에서 다시 선택해 주세요.',
    );
  const deadlineDate = input.recruitmentDeadline.date;
  if (
    !deadlineDate ||
    deadlineDate < referenceDate ||
    deadlineDate > contest.timing.closing.sourceDate
  )
    return issue(
      'VALIDATION_ERROR',
      '팀 모집 마감은 오늘부터 공모전 마감일까지 설정해 주세요.',
      'recruitmentDeadline',
    );
  return null;
}

// [출처 5] 팀 생성: 팀·팀장 소속, 같은 공모전의 본인 대기 지원 폐기
export function createDemoTeam(
  db: DemoDatabase,
  input: NewTeamInput,
  accountId: string,
  ids: { teamId: string; membershipId: string },
  now = referenceNow,
): Transition {
  const problem = createTeamIssue(input, db, accountId, now);
  if (problem) return { error: problem };
  const contest = contestOf(db, input.contestId)!;
  // [출처 5] 원문 날짜·시각·시간대를 모두 반영해 UTC 경계와 보완 정보를 계산
  const deadline = interpretDeadline(input.recruitmentDeadline);
  const createdAt = stamp(now);
  const solo = input.capacity === 1;
  const team: TeamRecord = {
    id: ids.teamId,
    version: '1',
    contestId: contest.id,
    name: input.name.trim(),
    introduction: input.introduction.trim(),
    roleCodes: solo ? [] : [...input.roleCodes],
    capacity: String(input.capacity),
    recruitmentState: solo ? 'closed' : 'open',
    closedReason: solo ? 'capacity_reached' : null,
    recruitmentEndsAt: deadline.endsAt,
    createdAt,
    recruitmentDeadline: deadline.interpretation,
    ownerAccountId: accountId,
  };
  return {
    db: {
      ...db,
      teams: [...db.teams, team],
      memberships: [
        ...db.memberships,
        {
          membershipId: ids.membershipId,
          teamId: team.id,
          accountId,
          membershipRole: 'leader',
          roleCode: null,
          joinedAt: createdAt,
          endedAt: null,
        },
      ],
      applications: discardPending(
        db.applications,
        accountId,
        contest.id,
        null,
        'team_created_elsewhere',
        { teamId: team.id },
        now,
      ),
    },
  };
}

// 지원받은 팀장에게 보이는 현재 전체 프로필(지원 당시 사본이 아님)
export function applicantVisibleProfile(
  db: DemoDatabase,
  application: Pick<Application, 'applicantAccountId'>,
): Profile | undefined {
  return profileOf(db, application.applicantAccountId);
}
