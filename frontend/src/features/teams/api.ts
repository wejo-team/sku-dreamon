/**
 * [참조 출처]
 * 1. docs/api/teams.md#endpoints - 공개 팀 탐색 3개, 팀 생성·워크스페이스 5개
 * 2. docs/api/teams.md#queries - page, pageSize, q, roleCode, recruitingOnly, contestId(GET /teams만)
 * 3. docs/api/teams.md#values - RecruitmentState open|closed
 * 4. docs/api/teams.md#team-create, #deadline-input - TeamCreate, DeadlineInput
 * 5. docs/api/teams.md#team-summary, #team - TeamSummary, Team(+ownerAccountId, contest)
 * 6. docs/api/teams.md#team-member, #team-space, #workspace-team - TeamMember, TeamSpace, WorkspaceTeam
 * 7. docs/api/teams.md#action-results, #transitions - RecruitmentResult, 생성 201/재전송 200, VersionedAction
 */

import { z } from 'zod';
import { apiRequest, apiRequestWithResponse, withQuery } from '@/lib/api';
import {
  CatalogCode,
  DateString,
  Id,
  PositiveBigInt,
  PositiveSafeInteger,
  SafeInteger,
  TimeZoneName,
  Timestamp,
  Version,
  VersionedAction,
  page,
  success,
  trimmedText,
  uniqueCodes,
} from '@/lib/api-contract';
import {
  ContestSummary,
  DeadlineInterpretation,
} from '@/features/contests/api';
import { Profile } from '@/features/profiles/api';

const unique = (codes: string[]) => new Set(codes).size === codes.length;

// [출처 3]
export const RecruitmentState = z.enum(['open', 'closed']);
export type RecruitmentState = z.infer<typeof RecruitmentState>;
export const MembershipRole = z.enum(['leader', 'member']);
export type MembershipRole = z.infer<typeof MembershipRole>;

// [출처 4] 원문 마감 입력
export const DeadlineInput = z
  .object({
    date: DateString,
    time: z
      .string()
      .regex(/^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/)
      .nullable()
      .optional(),
    timeZone: TimeZoneName.nullable().optional(),
  })
  .strict();
export type DeadlineInput = z.infer<typeof DeadlineInput>;

// [출처 4] capacity="1"이면 roleCodes=[], 2명 이상이면 1~6개
export const TeamCreate = z
  .object({
    requestId: Id,
    contestId: Id,
    // NFC·trim 후 코드 포인트 기준(docs/api/teams.md#team-create)
    name: trimmedText(2, 40),
    introduction: trimmedText(10, 1000),
    capacity: PositiveBigInt,
    roleCodes: z.array(CatalogCode).max(6).refine(unique),
    recruitmentDeadline: DeadlineInput,
  })
  .strict()
  .refine(
    (value) =>
      value.capacity === '1'
        ? value.roleCodes.length === 0
        : value.roleCodes.length >= 1,
    { path: ['roleCodes'], message: '정원에 맞는 모집 역할 수가 아닙니다.' },
  );
export type TeamCreate = z.infer<typeof TeamCreate>;

// [출처 5] 팀 목록
export const TeamSummary = z
  .object({
    id: Id,
    version: Version,
    contestId: Id,
    contestTitle: z.string(),
    name: z.string(),
    introduction: z.string(),
    fieldCodes: uniqueCodes(z.array(CatalogCode).max(3)),
    roleCodes: uniqueCodes(z.array(CatalogCode).max(6)),
    capacity: PositiveBigInt,
    memberCount: PositiveSafeInteger,
    recruitmentState: RecruitmentState,
    closedReason: z.enum(['capacity_reached', 'leader_closed']).nullable(),
    recruitmentEndsAt: Timestamp,
    isRecruiting: z.boolean(),
    isDemo: z.boolean(),
    createdAt: Timestamp,
    recruitmentDeadline: DeadlineInterpretation,
  })
  .strict();
export type TeamSummary = z.infer<typeof TeamSummary>;

// [출처 5] TeamSummary 전체 + ownerAccountId, contest
export const TeamDetail = TeamSummary.extend({
  ownerAccountId: Id,
  contest: ContestSummary,
}).strict();
export type TeamDetail = z.infer<typeof TeamDetail>;

// [출처 6] 소속 표시와 프로필 열람 분리. profile은 권한이 있을 때만
export const TeamMember = z
  .object({
    membershipId: Id,
    accountId: Id,
    realName: z.string(),
    isDemo: z.boolean(),
    membershipRole: MembershipRole,
    roleCode: CatalogCode.nullable(),
    joinedAt: Timestamp,
    profile: Profile.nullable(),
  })
  .strict();
export type TeamMember = z.infer<typeof TeamMember>;

// [출처 6] pendingApplicationCount는 팀장에게만 값, 일반 팀원은 null
export const TeamSpace = z
  .object({
    team: TeamDetail,
    members: z.array(TeamMember).min(1),
    viewerRole: MembershipRole,
    pendingApplicationCount: SafeInteger.nullable(),
  })
  .strict();
export type TeamSpace = z.infer<typeof TeamSpace>;

// [출처 6]
export const WorkspaceTeam = z
  .object({
    team: TeamSummary,
    membershipId: Id,
    membershipRole: MembershipRole,
    roleCode: CatalogCode.nullable(),
    pendingApplicationCount: SafeInteger.nullable(),
  })
  .strict();
export type WorkspaceTeam = z.infer<typeof WorkspaceTeam>;

// [출처 7]
export const RecruitmentResult = z.object({ team: TeamSummary }).strict();
export type RecruitmentResult = z.infer<typeof RecruitmentResult>;

// [출처 2]
export type TeamListQuery = {
  page?: number;
  pageSize?: number;
  q?: string;
  roleCode?: string;
  recruitingOnly?: boolean;
};

// [출처 1, 2] GET /contests/{contestId}/teams → 200 Page<TeamSummary>
export async function listContestTeams(
  contestId: string,
  query: TeamListQuery = {},
  signal?: AbortSignal,
) {
  return page(TeamSummary).parse(
    await apiRequest(
      withQuery(`/contests/${encodeURIComponent(contestId)}/teams`, query),
      { signal },
    ),
  );
}

// [출처 1, 2] GET /teams → 200 Page<TeamSummary>
export async function listTeams(
  query: TeamListQuery & { contestId?: string } = {},
  signal?: AbortSignal,
) {
  return page(TeamSummary).parse(
    await apiRequest(withQuery('/teams', query), { signal }),
  );
}

// [출처 1, 5] GET /teams/{teamId} → 200 Success<Team>
export async function getTeam(teamId: string, signal?: AbortSignal) {
  return success(TeamDetail).parse(
    await apiRequest(`/teams/${encodeURIComponent(teamId)}`, { signal }),
  ).data;
}

// [출처 1, 7] POST /teams → 첫 생성 201, 같은 requestId·본문 재전송 200. created로 구분합니다.
export async function createTeam(body: TeamCreate, signal?: AbortSignal) {
  const response = await apiRequestWithResponse('/teams', {
    method: 'POST',
    json: TeamCreate.parse(body),
    signal,
  });
  return {
    team: success(TeamDetail).parse(response.body).data,
    created: response.status === 201,
  };
}

// [출처 1, 6] GET /me/teams → 200 Page<WorkspaceTeam>
export async function listMyTeams(
  query: { page?: number; pageSize?: number } = {},
  signal?: AbortSignal,
) {
  return page(WorkspaceTeam).parse(
    await apiRequest(withQuery('/me/teams', query), { signal }),
  );
}

// [출처 1, 6] GET /teams/{teamId}/space → 200 Success<TeamSpace>. 현재 소속이 아니면 403
export async function getTeamSpace(teamId: string, signal?: AbortSignal) {
  return success(TeamSpace).parse(
    await apiRequest(`/teams/${encodeURIComponent(teamId)}/space`, { signal }),
  ).data;
}

// [출처 1, 7] PUT /teams/{teamId}/recruitment/closure → 200 Success<RecruitmentResult>
export async function closeRecruitment(
  teamId: string,
  body: VersionedAction,
  signal?: AbortSignal,
) {
  const response = await apiRequest(
    `/teams/${encodeURIComponent(teamId)}/recruitment/closure`,
    { method: 'PUT', json: VersionedAction.parse(body), signal },
  );
  return success(RecruitmentResult).parse(response).data;
}

// [출처 1, 7] PUT /teams/{teamId}/recruitment/reopening → 200 Success<RecruitmentResult>
export async function reopenRecruitment(
  teamId: string,
  body: VersionedAction,
  signal?: AbortSignal,
) {
  const response = await apiRequest(
    `/teams/${encodeURIComponent(teamId)}/recruitment/reopening`,
    { method: 'PUT', json: VersionedAction.parse(body), signal },
  );
  return success(RecruitmentResult).parse(response).data;
}
