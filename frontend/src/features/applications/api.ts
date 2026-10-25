/**
 * [참조 출처]
 * 1. docs/api/applications.md#endpoints - 지원 9개 API의 메서드·경로·성공 응답
 * 2. docs/api/applications.md#queries - page, pageSize, status
 * 3. docs/api/applications.md#values - ApplicationStatus
 * 4. docs/api/applications.md#application-create - ApplicationCreate { requestId, roleCode, message }
 * 5. docs/api/applications.md#application - Application 필드
 * 6. docs/api/applications.md#my-application, #applicant - MyApplication, Applicant
 * 7. docs/api/applications.md#action-results, #transitions - SelectionResult, CancellationResult, 생성 201/재전송 200
 */

import { z } from 'zod';
import { apiRequest, apiRequestWithResponse, withQuery } from '@/lib/api';
import {
  CatalogCode,
  Id,
  Timestamp,
  Version,
  VersionedAction,
  page,
  success,
} from '@/lib/api-contract';
import { Profile } from '@/features/profiles/api';
import { TeamSummary } from '@/features/teams/api';

// [출처 3]
export const ApplicationStatus = z.enum([
  'submitted',
  'reviewing',
  'selected',
  'rejected',
  'canceled',
  'discarded',
]);
export type ApplicationStatus = z.infer<typeof ApplicationStatus>;

// [출처 4] message는 생략·null·trim 후 빈 본문이면 null로 정규화
export const ApplicationCreate = z
  .object({
    requestId: Id,
    roleCode: CatalogCode,
    message: z.string().max(1000).nullable().optional(),
  })
  .strict();
export type ApplicationCreate = z.infer<typeof ApplicationCreate>;

// [출처 5] discardReason은 discarded일 때만 값. 원인 ID 두 필드는 동시에 값을 갖지 않음
export const Application = z
  .object({
    id: Id,
    version: Version,
    teamId: Id,
    contestId: Id,
    applicantAccountId: Id,
    roleCode: CatalogCode,
    message: z.string().max(1000).nullable(),
    status: ApplicationStatus,
    discardReason: z
      .enum(['selected_elsewhere', 'team_created_elsewhere'])
      .nullable(),
    discardedByApplicationId: Id.nullable(),
    discardedByTeamId: Id.nullable(),
    submittedAt: Timestamp,
    updatedAt: Timestamp,
  })
  .strict()
  .superRefine((value, ctx) => {
    if ((value.status === 'discarded') !== (value.discardReason !== null))
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['discardReason'],
        message: 'discardReason은 discarded일 때만 값을 가집니다.',
      });
    if (value.discardedByApplicationId && value.discardedByTeamId)
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['discardedByTeamId'],
        message: '폐기 원인 ID는 하나만 가질 수 있습니다.',
      });
  });
export type Application = z.infer<typeof Application>;

// [출처 6]
export const MyApplication = z
  .object({
    application: Application,
    team: TeamSummary,
    isCurrentMember: z.boolean(),
  })
  .strict();
export type MyApplication = z.infer<typeof MyApplication>;

export const Applicant = z
  .object({
    application: Application,
    profile: Profile,
    isSelectionCandidate: z.boolean(),
  })
  .strict();
export type Applicant = z.infer<typeof Applicant>;

// [출처 7]
export const SelectionResult = z
  .object({ application: Application, team: TeamSummary, membershipId: Id })
  .strict();
export type SelectionResult = z.infer<typeof SelectionResult>;
export const CancellationResult = z
  .object({ application: Application, membershipEnded: z.boolean() })
  .strict();
export type CancellationResult = z.infer<typeof CancellationResult>;

// [출처 2]
export type ApplicationListQuery = {
  page?: number;
  pageSize?: number;
  status?: ApplicationStatus;
};

const applicationPath = (applicationId: string, suffix = '') =>
  `/applications/${encodeURIComponent(applicationId)}${suffix}`;

// [출처 1, 7] POST /teams/{teamId}/applications → 첫 접수 201, 같은 시도 재전송 200
export async function createApplication(
  teamId: string,
  body: ApplicationCreate,
  signal?: AbortSignal,
) {
  const response = await apiRequestWithResponse(
    `/teams/${encodeURIComponent(teamId)}/applications`,
    { method: 'POST', json: ApplicationCreate.parse(body), signal },
  );
  return {
    application: success(Application).parse(response.body).data,
    created: response.status === 201,
  };
}

// [출처 1, 6] GET /me/applications → 200 Page<MyApplication>
export async function listMyApplications(
  query: ApplicationListQuery = {},
  signal?: AbortSignal,
) {
  return page(MyApplication).parse(
    await apiRequest(withQuery('/me/applications', query), { signal }),
  );
}

// [출처 1, 5] GET /applications/{applicationId} → 200 Success<Application>
export async function getApplication(
  applicationId: string,
  signal?: AbortSignal,
) {
  return success(Application).parse(
    await apiRequest(applicationPath(applicationId), { signal }),
  ).data;
}

// [출처 1, 7] PUT /applications/{applicationId}/cancellation → 200 Success<CancellationResult>
export async function cancelApplication(
  applicationId: string,
  body: VersionedAction,
  signal?: AbortSignal,
) {
  const response = await apiRequest(
    applicationPath(applicationId, '/cancellation'),
    { method: 'PUT', json: VersionedAction.parse(body), signal },
  );
  return success(CancellationResult).parse(response).data;
}

// [출처 1, 6] GET /teams/{teamId}/applicants → 200 Page<Applicant>
export async function listTeamApplicants(
  teamId: string,
  query: ApplicationListQuery = {},
  signal?: AbortSignal,
) {
  return page(Applicant).parse(
    await apiRequest(
      withQuery(`/teams/${encodeURIComponent(teamId)}/applicants`, query),
      { signal },
    ),
  );
}

// [출처 1, 6] GET /applications/{applicationId}/applicant → 200 Success<Applicant>
export async function getApplicant(
  applicationId: string,
  signal?: AbortSignal,
) {
  return success(Applicant).parse(
    await apiRequest(applicationPath(applicationId, '/applicant'), { signal }),
  ).data;
}

// [출처 1, 7] 팀장의 상태 변경: 검토 시작·미선발 → Success<Application>
async function putApplicationAction(
  applicationId: string,
  action: 'review-start' | 'rejection',
  body: VersionedAction,
  signal?: AbortSignal,
) {
  const response = await apiRequest(
    applicationPath(applicationId, `/${action}`),
    { method: 'PUT', json: VersionedAction.parse(body), signal },
  );
  return success(Application).parse(response).data;
}

// [출처 1] PUT /applications/{applicationId}/review-start
export const startApplicationReview = (
  applicationId: string,
  body: VersionedAction,
  signal?: AbortSignal,
) => putApplicationAction(applicationId, 'review-start', body, signal);

// [출처 1] PUT /applications/{applicationId}/rejection
export const rejectApplication = (
  applicationId: string,
  body: VersionedAction,
  signal?: AbortSignal,
) => putApplicationAction(applicationId, 'rejection', body, signal);

// [출처 1, 7] PUT /applications/{applicationId}/selection → 200 Success<SelectionResult>
export async function selectApplication(
  applicationId: string,
  body: VersionedAction,
  signal?: AbortSignal,
) {
  const response = await apiRequest(
    applicationPath(applicationId, '/selection'),
    { method: 'PUT', json: VersionedAction.parse(body), signal },
  );
  return success(SelectionResult).parse(response).data;
}
