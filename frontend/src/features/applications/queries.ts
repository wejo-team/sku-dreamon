/**
 * [참조 출처]
 * 1. docs/api/applications.md#endpoints - 지원·본인 조회·취소, 팀장 지원자 조회·검토 시작·미선발·선발
 * 2. docs/api/applications.md#queries - status·page·pageSize
 * 3. docs/api/applications.md#transitions - expectedVersion, 신규 지원 requestId 재전송
 * 4. docs/development/frontend.md - 「API와 query」 mutation 성공 시 영향받은 query 무효화
 */

import {
  queryOptions,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import {
  cancelApplication,
  createApplication,
  getApplicant,
  getApplication,
  listMyApplications,
  listTeamApplicants,
  rejectApplication,
  selectApplication,
  startApplicationReview,
  type ApplicationCreate,
  type ApplicationListQuery,
} from '@/features/applications/api';
import { invalidateParticipation, queryKeys } from '@/lib/query-keys';

// [출처 1, 2] 내 지원은 최대 페이지 크기로 한 번에 받습니다.
export const myApplicationsQueryOptions = (
  query: ApplicationListQuery = { pageSize: 100 },
) =>
  queryOptions({
    queryKey: queryKeys.myApplications(query),
    queryFn: ({ signal }) => listMyApplications(query, signal),
  });

export const applicationQueryOptions = (applicationId: string) =>
  queryOptions({
    queryKey: queryKeys.application(applicationId),
    queryFn: ({ signal }) => getApplication(applicationId, signal),
  });

export const applicantsQueryOptions = (
  teamId: string,
  query: ApplicationListQuery = { pageSize: 100 },
) =>
  queryOptions({
    queryKey: queryKeys.applicants(teamId, query),
    queryFn: ({ signal }) => listTeamApplicants(teamId, query, signal),
  });

export const applicantQueryOptions = (applicationId: string) =>
  queryOptions({
    queryKey: queryKeys.applicant(applicationId),
    queryFn: ({ signal }) => getApplicant(applicationId, signal),
  });

// [출처 3, 4] 지원·취소·검토·선발은 팀 인원·모집 상태·알림을 함께 바꿉니다.
function useParticipationMutation<Input, Output>(
  request: (input: Input) => Promise<Output>,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: () => invalidateParticipation(client),
  });
}

export const useApply = () =>
  useParticipationMutation(
    ({ teamId, body }: { teamId: string; body: ApplicationCreate }) =>
      createApplication(teamId, body),
  );

type VersionedInput = { applicationId: string; expectedVersion: string };

export const useCancelApplication = () =>
  useParticipationMutation(
    ({ applicationId, expectedVersion }: VersionedInput) =>
      cancelApplication(applicationId, { expectedVersion }),
  );

export const useStartReview = () =>
  useParticipationMutation(
    ({ applicationId, expectedVersion }: VersionedInput) =>
      startApplicationReview(applicationId, { expectedVersion }),
  );

export const useRejectApplication = () =>
  useParticipationMutation(
    ({ applicationId, expectedVersion }: VersionedInput) =>
      rejectApplication(applicationId, { expectedVersion }),
  );

export const useSelectApplication = () =>
  useParticipationMutation(
    ({ applicationId, expectedVersion }: VersionedInput) =>
      selectApplication(applicationId, { expectedVersion }),
  );
