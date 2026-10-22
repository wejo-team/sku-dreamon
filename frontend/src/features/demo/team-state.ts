/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/team-state.ts - 팀·지원 상태 전이 원본
 * 2. docs/specs/team-recruitment.md#team-state-transitions - 모집 상태와 전이
 * 3. docs/specs/team-recruitment.md#parallel-applications - 동시 지원, 선발 시 같은 공모전의 다른 대기 지원 폐기
 * 4. docs/specs/team-recruitment.md#recruitment-reopening - 정원 충족 후 자동 재개 없음, 팀장 확인 후 재개
 * 5. docs/specs/team-recruitment.md#membership-capacity - 팀장 포함 정원, 선발 즉시 확정·자리 차감, 취소 시 반환
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import { profileToPerson } from '@/features/demo/data';
import {
  contests,
  roleOptions,
  type Applicant,
  type Application,
  type ApplicationStatus,
  type Profile,
  type Team,
} from '@/features/demo/data';
import {
  contestDeadline,
  contestStatus,
  hasConfirmedMemberLimit,
  isContestOpen,
  memberLimitLabel,
  referenceNow,
  scheduleInstant,
} from '@/features/demo/contest-state';
import {
  missingProfileFields,
  profileTextLength,
} from '@/features/demo/profile-fields';

// Reference fixtures intentionally use a fixed date so archived designs stay reviewable.
export const referenceDate = '2026-10-18';
export const dateValue = (date: string) => date.replaceAll('.', '-');
export type NewTeam = Omit<
  Team,
  'id' | 'owner' | 'members' | 'status' | 'memberProfiles'
>;
export type TeamActivity = {
  teams: Team[];
  applications: Application[];
  applicants: Applicant[];
};

export function isTeamMember(team: Team, personId = 'me') {
  return (
    (personId === 'me' && team.owner) ||
    Boolean(team.memberProfiles?.some((member) => member.id === personId))
  );
}

export function teamRecruitmentDeadline(
  team: Pick<Team, 'recruitmentDeadline' | 'contestId'>,
): number {
  const contest = contests.find((item) => item.id === team.contestId);
  const teamDeadline = scheduleInstant(
    team.recruitmentDeadline,
    'Asia/Seoul',
    true,
  );
  return contest
    ? Math.min(teamDeadline, contestDeadline(contest))
    : teamDeadline;
}

// [출처 2, 5] 모집 가능 여부 판정(기한·정원·상태)
export function recruitmentIssue(
  team: Team,
  now = referenceNow,
): string | null {
  const contest = contests.find((item) => item.id === team.contestId);
  if (!contest || contestStatus(contest, now) === 'closed')
    return '공모전 접수가 마감되어 지원할 수 없어요.';
  if (contestStatus(contest, now) === 'upcoming')
    return '공모전 접수가 시작되면 지원할 수 있어요.';
  if (!['모집중', '지원자검토'].includes(team.status))
    return '모집이 마감되어 지금은 지원할 수 없어요.';
  if (now >= teamRecruitmentDeadline(team))
    return '팀 모집 기한이 지나 지원할 수 없어요.';
  if (team.members >= team.capacity) return '팀 정원이 모두 찼어요.';
  return null;
}

// [출처 4] 재개 불가 사유
export function recruitmentReopeningIssue(team: Team, now = referenceNow) {
  if (!team.owner) return '팀장만 모집을 다시 시작할 수 있어요.';
  if (team.status !== '모집마감') return '마감된 모집만 다시 시작할 수 있어요.';
  if (team.members >= team.capacity)
    return '팀 정원이 모두 차서 다시 모집할 수 없어요.';
  const contest = contests.find((item) => item.id === team.contestId);
  if (!contest || contestStatus(contest, now) === 'closed')
    return '공모전 접수가 마감되어 다시 모집할 수 없어요.';
  if (contestStatus(contest, now) === 'upcoming')
    return '공모전 접수가 시작되면 다시 모집할 수 있어요.';
  if (now >= teamRecruitmentDeadline(team))
    return '팀 모집 기한이 지나 다시 모집할 수 없어요.';
  return null;
}

// [출처 4] 팀장 확인 후 재개
export function reopenTeamRecruitment(
  state: TeamActivity,
  teamId: string,
  now = referenceNow,
): TeamActivity | null {
  const team = state.teams.find((item) => item.id === teamId);
  if (!team || recruitmentReopeningIssue(team, now)) return null;
  return {
    ...state,
    teams: state.teams.map((item) =>
      item.id === teamId ? { ...item, status: '모집중' } : item,
    ),
  };
}

// Selection after closing remains TEAM-02/03 TBD; AI review has separate access rules.
export function selectionScenario(
  team: Team,
): 'ready' | 'full' | 'not-modeled' {
  if (team.members >= team.capacity) return 'full';
  return recruitmentIssue(team) ? 'not-modeled' : 'ready';
}

// [출처 2] 모집 상태 문구
export function teamStatusLabel(team: Team) {
  if (team.status === '팀원확정') return '팀원 확정';
  if (team.status === '모집마감') return '모집 마감';
  if (team.members >= team.capacity) return '정원 충족';
  const contest = contests.find((item) => item.id === team.contestId);
  if (contest && contestStatus(contest) === 'upcoming') return '모집 예정';
  if (recruitmentIssue(team)) return '모집 마감';
  return team.status === '지원자검토' ? '지원자 검토' : '모집 중';
}

// [출처 5] 팀 생성 조건
export function createTeamIssue(input: NewTeam, teams: Team[]) {
  const contest = contests.find((item) => item.id === input.contestId);
  if (!contest || !isContestOpen(contest))
    return '접수 중인 공모전을 선택해 주세요.';
  if (
    teams.some(
      (team) => team.contestId === input.contestId && isTeamMember(team),
    )
  )
    return '이미 이 공모전의 팀에 소속되어 있어요. 내 팀에서 확인해 주세요.';
  const nameLength = profileTextLength(input.name);
  if (nameLength < 2 || nameLength > 40)
    return '팀 이름을 2~40자로 입력해 주세요.';
  const summaryLength = profileTextLength(input.summary);
  if (summaryLength < 10 || summaryLength > 1000)
    return '팀 소개와 목표를 10~1,000자로 입력해 주세요.';
  if (!Number.isInteger(input.capacity) || input.capacity < 1)
    return '팀장 포함 총 정원을 1명 이상 입력해 주세요.';
  if (!hasConfirmedMemberLimit(contest))
    return '공식 참가 인원을 확인한 뒤 팀을 만들 수 있어요.';
  if (
    (contest.minMembers != null && input.capacity < contest.minMembers) ||
    (contest.memberLimit === 'range' &&
      contest.maxMembers != null &&
      input.capacity > contest.maxMembers)
  )
    return `공식 참가 인원 ${memberLimitLabel(contest)}에 맞춰 총 정원을 입력해 주세요.`;
  if (
    input.capacity >= 2 &&
    (input.roles.length < 1 ||
      input.roles.length > 6 ||
      input.roles.some((role) => !roleOptions.includes(role)) ||
      new Set(input.roles).size !== input.roles.length)
  )
    return '모집할 역할을 1~6개 선택해 주세요.';
  if (input.capacity === 1 && input.roles.length)
    return '1명인 팀은 모집할 역할을 선택하지 않아요.';
  if (
    !input.recruitmentDeadline ||
    input.recruitmentDeadline < referenceDate ||
    input.recruitmentDeadline > dateValue(contest.deadline).slice(0, 10)
  )
    return '팀 모집 마감은 오늘부터 공모전 마감일까지 설정해 주세요.';
  return null;
}

// [출처 2, 3] 지원 제출
export function applyToTeam(
  state: TeamActivity,
  profile: Profile,
  teamId: string,
  role: string,
  message: string,
  id: string,
): TeamActivity | null {
  const team = state.teams.find((item) => item.id === teamId);
  if (
    !team ||
    !profile.visibility.discoverable ||
    isTeamMember(team) ||
    recruitmentIssue(team) ||
    !roleOptions.includes(role) ||
    profileTextLength(message) > 1000 ||
    missingProfileFields(profile).length ||
    state.applications.some(
      (item) => item.teamId === teamId && item.status !== '지원취소',
    )
  )
    return null;
  const application: Application = {
    id,
    personId: 'me',
    teamId,
    role,
    message: message.trim(),
    status: '지원완료',
  };
  return {
    ...state,
    applications: [...state.applications, application],
    applicants: [
      ...state.applicants,
      { ...application, personId: 'me', name: profile.name, interests: [] },
    ],
  };
}

// [출처 3, 5] 선발: 팀원 확정·자리 차감·다른 대기 지원 폐기
export function selectTeamApplicant(
  state: TeamActivity,
  applicantId: string,
  profile: Profile,
): TeamActivity | null {
  const applicant = state.applicants.find((item) => item.id === applicantId);
  const team = state.teams.find((item) => item.id === applicant?.teamId);
  if (
    !applicant ||
    !team?.owner ||
    !['지원완료', '검토중'].includes(applicant.status) ||
    selectionScenario(team) !== 'ready'
  )
    return null;
  const personId = applicant.personId;
  if (
    state.teams.some(
      (item) =>
        item.contestId === team.contestId && isTeamMember(item, personId),
    )
  )
    return null;
  const name =
    personId === 'me'
      ? profile.name
      : (applicant.profile?.name ?? applicant.name);
  const applicationStatus = (
    item: Application | Applicant,
  ): ApplicationStatus => {
    if (item.id === applicantId) return '선발';
    const sameContest = state.teams.some(
      (other) => other.id === item.teamId && other.contestId === team.contestId,
    );
    return (item.personId ?? 'me') === personId &&
      item.teamId !== team.id &&
      sameContest &&
      ['지원완료', '검토중'].includes(item.status)
      ? '폐기'
      : item.status;
  };
  return {
    teams: state.teams.map((item) =>
      item.id === team.id
        ? {
            ...item,
            members: item.members + 1,
            status:
              item.members + 1 >= item.capacity ? '모집마감' : item.status,
            memberProfiles: [
              ...(item.memberProfiles ?? []),
              { id: personId, name, role: applicant.role },
            ],
          }
        : item,
    ),
    applicants: state.applicants.map((item) => ({
      ...item,
      status: applicationStatus(item),
    })),
    applications: state.applications.map((item) => ({
      ...item,
      status: applicationStatus(item),
    })),
  };
}

// [출처 5] 취소: 자리 반환, 폐기 이력 복원 없음
export function cancelTeamApplication(
  state: TeamActivity,
  applicationId: string,
): TeamActivity | null {
  const application = state.applications.find(
    (item) => item.id === applicationId,
  );
  if (
    !application ||
    !['지원완료', '검토중', '선발'].includes(application.status)
  )
    return null;
  return {
    teams: state.teams.map((team) =>
      team.id === application.teamId &&
      application.status === '선발' &&
      isTeamMember(team) &&
      !team.owner
        ? {
            ...team,
            members: Math.max(1, team.members - 1),
            status:
              team.members >= team.capacity &&
              ['모집중', '지원자검토'].includes(team.status)
                ? '모집마감'
                : team.status,
            memberProfiles: (team.memberProfiles ?? []).filter(
              (member) => member.id !== 'me',
            ),
          }
        : team,
    ),
    applications: state.applications.map((item) =>
      item.id === applicationId ? { ...item, status: '지원취소' } : item,
    ),
    applicants: state.applicants.map((item) =>
      item.id === applicationId ? { ...item, status: '지원취소' } : item,
    ),
  };
}

// [출처 1] 지원받은 팀장에게 보이는 현재 프로필
export function applicantVisibleProfile(
  applicant: Applicant,
  currentProfile: Profile,
) {
  const profile =
    applicant.personId === 'me' ? currentProfile : applicant.profile;
  return profile
    ? profileToPerson(profile, applicant.personId)
    : {
        id: applicant.personId,
        name: applicant.name,
        roles: [applicant.role],
        interests: applicant.interests,
        skills: [],
      };
}
