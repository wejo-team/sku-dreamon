import { profileToPerson } from './data';
import {
  contests,
  roleOptions,
  type Applicant,
  type Application,
  type Profile,
  type Team,
} from './data';
import { missingProfileFields } from './profile-fields';

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

export function recruitmentIssue(team: Team): string | null {
  const contest = contests.find((item) => item.id === team.contestId);
  if (
    !contest ||
    contest.status === 'closed' ||
    dateValue(contest.deadline) < referenceDate
  )
    return '공모전 접수가 마감되어 지원할 수 없어요.';
  if (team.status === '모집마감' || team.status === '팀원확정')
    return '모집이 마감되어 지금은 지원할 수 없어요.';
  if (
    team.recruitmentDeadline &&
    dateValue(team.recruitmentDeadline) < referenceDate
  )
    return '팀 모집 기한이 지나 지원할 수 없어요.';
  if (team.members >= team.capacity) return '팀 정원이 모두 찼어요.';
  return null;
}

// Existing-applicant behavior after closing/deadlines is still TEAM-02/03 TBD.
// Those fixture scenarios are deliberately not modeled; this is not a server
// eligibility rule, and must not reuse the new-application rejection message.
export function selectionScenario(
  team: Team,
): 'ready' | 'full' | 'not-modeled' {
  if (team.members >= team.capacity) return 'full';
  const contest = contests.find((item) => item.id === team.contestId);
  if (
    !contest ||
    contest.status === 'closed' ||
    dateValue(contest.deadline) < referenceDate ||
    !['모집중', '지원자검토'].includes(team.status) ||
    (team.recruitmentDeadline &&
      dateValue(team.recruitmentDeadline) < referenceDate)
  )
    return 'not-modeled';
  return 'ready';
}

export function teamStatusLabel(team: Team) {
  if (team.status === '팀원확정') return '팀원 확정';
  if (team.status === '모집마감') return '모집 마감';
  if (team.members >= team.capacity) return '정원 충족';
  if (recruitmentIssue(team)) return '모집 마감';
  return team.status === '지원자검토' ? '지원자 검토' : '모집 중';
}

export function createTeamIssue(input: NewTeam, teams: Team[]) {
  const contest = contests.find((item) => item.id === input.contestId);
  if (
    !contest ||
    contest.status === 'closed' ||
    dateValue(contest.deadline) < referenceDate
  )
    return '모집 중인 공모전을 선택해 주세요.';
  if (
    teams.some(
      (team) => team.contestId === input.contestId && isTeamMember(team),
    )
  )
    return '이미 이 공모전의 팀에 소속되어 있어요. 내 팀에서 확인해 주세요.';
  if (!Number.isInteger(input.capacity) || input.capacity < 1)
    return '팀장 포함 총 정원을 1명 이상 입력해 주세요.';
  if (
    input.kind === 'entry' &&
    ((contest.minMembers != null && input.capacity < contest.minMembers) ||
      (contest.maxMembers != null && input.capacity > contest.maxMembers))
  )
    return `공식 참가 인원 ${contest.minMembers ?? 1}~${contest.maxMembers ?? '제한 없음'}명에 맞춰 총 정원을 입력해 주세요.`;
  if (contest.participation === 'individual' && input.kind !== 'preparation')
    return '개인 참가 공모전은 함께 준비하는 팀으로 만들 수 있어요.';
  if (
    !input.recruitmentDeadline ||
    input.recruitmentDeadline < referenceDate ||
    input.recruitmentDeadline > dateValue(contest.deadline)
  )
    return '팀 모집 마감은 오늘부터 공모전 마감일까지 설정해 주세요.';
  return null;
}

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
    isTeamMember(team) ||
    recruitmentIssue(team) ||
    !roleOptions.includes(role) ||
    message.trim().length > 1000 ||
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
  return {
    teams: state.teams.map((item) =>
      item.id === team.id
        ? {
            ...item,
            members: item.members + 1,
            memberProfiles: [
              ...(item.memberProfiles ?? []),
              { id: personId, name, role: applicant.role },
            ],
          }
        : item,
    ),
    applicants: state.applicants.map((item) =>
      item.id === applicantId ? { ...item, status: '선발' } : item,
    ),
    applications: state.applications.map((item) =>
      item.id === applicantId ? { ...item, status: '선발' } : item,
    ),
  };
}

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
