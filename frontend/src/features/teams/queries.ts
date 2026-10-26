/**
 * [참조 출처]
 * 1. docs/api/teams.md#endpoints - 공개 팀 탐색 3개, 팀 생성·내 팀·팀 공간·모집 종료/재개
 * 2. docs/api/teams.md#queries - q·roleCode·recruitingOnly·contestId·page·pageSize
 * 3. docs/api/teams.md#transitions - expectedVersion, 생성 requestId 재전송
 * 4. docs/development/frontend.md - 「API와 query」 query key에 조회 조건, mutation 성공 시 무효화
 * 5. docs/api/conventions.md#versioned-action - 409 후 다시 조회, 자동 재전송 없음
 */

import {
  queryOptions,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import {
  closeRecruitment,
  createTeam,
  getTeam,
  getTeamSpace,
  listContestTeams,
  listMyTeams,
  listTeams,
  reopenRecruitment,
  type TeamCreate,
  type TeamListQuery,
} from '@/features/teams/api';
import {
  invalidateParticipation,
  isConflict,
  queryKeys,
} from '@/lib/query-keys';

// [출처 1, 2]
export const teamsQueryOptions = (
  query: TeamListQuery & { contestId?: string } = {},
) =>
  queryOptions({
    queryKey: queryKeys.teams(query),
    queryFn: ({ signal }) => listTeams(query, signal),
  });

export const contestTeamsQueryOptions = (
  contestId: string,
  query: TeamListQuery = {},
) =>
  queryOptions({
    queryKey: queryKeys.contestTeams(contestId, query),
    queryFn: ({ signal }) => listContestTeams(contestId, query, signal),
  });

export const teamQueryOptions = (teamId: string) =>
  queryOptions({
    queryKey: queryKeys.team(teamId),
    queryFn: ({ signal }) => getTeam(teamId, signal),
  });

// 현재 팀장·팀원만 200, 아니면 403(화면은 접근 안내로 표시)
export const teamSpaceQueryOptions = (teamId: string) =>
  queryOptions({
    queryKey: queryKeys.teamSpace(teamId),
    queryFn: ({ signal }) => getTeamSpace(teamId, signal),
  });

// 내 팀은 페이지 크기 최대(100)로 한 번에 받습니다(한 계정의 소속 팀은 공모전 수 이하).
export const myTeamsQueryOptions = (
  query: { page?: number; pageSize?: number } = { pageSize: 100 },
) =>
  queryOptions({
    queryKey: queryKeys.myTeams(query),
    queryFn: ({ signal }) => listMyTeams(query, signal),
  });

// [출처 3, 4]
export function useCreateTeam() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: TeamCreate) => createTeam(body),
    onSuccess: () => invalidateParticipation(client),
  });
}

// [출처 3, 5] 모집 종료·재개. 409면 최신 팀 버전을 다시 받습니다.
export function useRecruitmentAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      teamId,
      expectedVersion,
      action,
    }: {
      teamId: string;
      expectedVersion: string;
      action: 'close' | 'reopen';
    }) =>
      (action === 'close' ? closeRecruitment : reopenRecruitment)(teamId, {
        expectedVersion,
      }),
    onSuccess: () => invalidateParticipation(client),
    onError: (error) =>
      isConflict(error) ? invalidateParticipation(client) : undefined,
  });
}
