/**
 * [참조 출처]
 * 1. docs/api/ai.md#conversation-endpoints - 현재 대화 API 6개, 202 + Location: /api/v1/ai/requests/{id}
 * 2. docs/api/ai.md#conversation-fields - ConversationCreate, Conversation, MessageCreate, AiMessage, ConversationView
 * 3. docs/api/ai.md#ai-control-fields - AiRetry, AiCancel { expectedAttempt }
 * 4. docs/api/ai.md#ai-request-fields - AiPurpose, AiRequestStatus, AiRequest, AiFailure, 목적별 참조·상태별 결과 조합
 * 5. docs/api/ai.md#applicant-endpoints - POST /applications/{applicationId}/ai-reviews, GET .../ai-review,
 *    POST /teams/{teamId}/applicant-recommendations
 * 6. docs/api/ai.md#result-fields - AiResult(kind 판별), ResourceCard, ChatResult, ProfileVersion,
 *    ApplicantReviewResult, ApplicantRecommendation, ApplicantRecommendationResult
 */

import { z } from 'zod';
import { apiRequest, apiRequestWithResponse } from '@/lib/api';
import {
  CatalogCode,
  Id,
  PositiveSafeInteger,
  Timestamp,
  Version,
  success,
} from '@/lib/api-contract';

// [출처 2] 첫 대화도 빈 객체 {}를 전송
export const ConversationCreate = z
  .object({ previousConversationId: Id.nullable().optional() })
  .strict();
export type ConversationCreate = z.infer<typeof ConversationCreate>;

export const Conversation = z.object({ id: Id, createdAt: Timestamp }).strict();
export type Conversation = z.infer<typeof Conversation>;

// [출처 2] content 1~1,000자, 공백만은 422. 초과 입력을 잘라 보내지 않음
export const MessageCreate = z
  .object({
    clientMessageId: Id,
    content: z
      .string()
      .min(1)
      .max(1000)
      .refine((value) => value.trim().length > 0, '공백만 보낼 수 없습니다.'),
  })
  .strict();
export type MessageCreate = z.infer<typeof MessageCreate>;

export const AiMessage = z
  .object({
    id: Id,
    clientMessageId: Id.nullable(),
    role: z.enum(['user', 'assistant']),
    content: z.string(),
    sequence: PositiveSafeInteger,
    createdAt: Timestamp,
  })
  .strict();
export type AiMessage = z.infer<typeof AiMessage>;

// [출처 3]
export const AiRetry = z
  .object({ expectedAttempt: PositiveSafeInteger })
  .strict();
export type AiRetry = z.infer<typeof AiRetry>;
export const AiCancel = z
  .object({ expectedAttempt: PositiveSafeInteger })
  .strict();
export type AiCancel = z.infer<typeof AiCancel>;

// [출처 6]
export const ResourceCard = z
  .object({
    kind: z.enum(['contest', 'team', 'person']),
    resourceId: Id,
    title: z.string(),
    reason: z.string(),
    fieldCodes: z.array(CatalogCode),
    roleCodes: z.array(CatalogCode),
    isDemo: z.boolean(),
  })
  .strict();
export type ResourceCard = z.infer<typeof ResourceCard>;

export const ChatResult = z
  .object({
    kind: z.literal('chat'),
    answer: z.string(),
    // 종류 합계 최대 3개
    cards: z.array(ResourceCard).max(3),
    generatedAt: Timestamp,
    referencesChanged: z.boolean(),
  })
  .strict();
export type ChatResult = z.infer<typeof ChatResult>;

export const ProfileVersion = z
  .object({ accountId: Id, usedVersion: Version, currentVersion: Version })
  .strict();
export type ProfileVersion = z.infer<typeof ProfileVersion>;

export const ApplicantReviewResult = z
  .object({
    kind: z.literal('applicant_review'),
    applicationId: Id,
    summary: z.string(),
    evidence: z.array(z.string()),
    // 정확히 1개
    profileVersions: z.array(ProfileVersion).length(1),
    isStale: z.boolean(),
    isSelectionCandidate: z.boolean(),
    generatedAt: Timestamp,
  })
  .strict();
export type ApplicantReviewResult = z.infer<typeof ApplicantReviewResult>;

export const ApplicantRecommendation = z
  .object({
    applicationId: Id,
    reason: z.string(),
    profileVersion: ProfileVersion,
  })
  .strict();
export type ApplicantRecommendation = z.infer<typeof ApplicantRecommendation>;

export const ApplicantRecommendationResult = z
  .object({
    kind: z.literal('applicant_recommendation'),
    summary: z.string(),
    candidates: z.array(ApplicantRecommendation),
    isStale: z.boolean(),
    generatedAt: Timestamp,
  })
  .strict();
export type ApplicantRecommendationResult = z.infer<
  typeof ApplicantRecommendationResult
>;

// [출처 6] 정확히 하나의 결과 객체
export const AiResult = z.discriminatedUnion('kind', [
  ChatResult,
  ApplicantReviewResult,
  ApplicantRecommendationResult,
]);
export type AiResult = z.infer<typeof AiResult>;

// [출처 4]
export const AiPurpose = z.enum([
  'chat',
  'applicant_review',
  'applicant_recommendation',
]);
export type AiPurpose = z.infer<typeof AiPurpose>;
export const AiRequestStatus = z.enum([
  'pending',
  'succeeded',
  'empty',
  'failed',
  'canceled',
]);
export type AiRequestStatus = z.infer<typeof AiRequestStatus>;

export const AiFailure = z
  .object({
    code: z.enum(['temporary_failure', 'invalid_output', 'context_changed']),
    message: z.string(),
    retryable: z.boolean(),
  })
  .strict();
export type AiFailure = z.infer<typeof AiFailure>;

// [출처 4] 목적별 값이 있어야 하는 참조 / 반드시 null인 참조
const referenceRules: Record<
  AiPurpose,
  {
    present: ('conversationId' | 'messageId' | 'teamId' | 'applicationId')[];
    absent: ('conversationId' | 'messageId' | 'teamId' | 'applicationId')[];
  }
> = {
  chat: {
    present: ['conversationId', 'messageId'],
    absent: ['teamId', 'applicationId'],
  },
  applicant_review: {
    present: ['teamId', 'applicationId'],
    absent: ['conversationId', 'messageId'],
  },
  applicant_recommendation: {
    present: ['teamId'],
    absent: ['conversationId', 'messageId', 'applicationId'],
  },
};

export const AiRequest = z
  .object({
    id: Id,
    purpose: AiPurpose,
    conversationId: Id.nullable(),
    messageId: Id.nullable(),
    teamId: Id.nullable(),
    applicationId: Id.nullable(),
    attempt: PositiveSafeInteger,
    status: AiRequestStatus,
    createdAt: Timestamp,
    updatedAt: Timestamp,
    result: AiResult.nullable(),
    failure: AiFailure.nullable(),
  })
  .strict()
  .superRefine((value, ctx) => {
    const issue = (path: string, message: string) =>
      ctx.addIssue({ code: z.ZodIssueCode.custom, path: [path], message });
    const rule = referenceRules[value.purpose];
    for (const key of rule.present)
      if (value[key] === null)
        issue(key, `${value.purpose}에는 ${key}가 필요합니다.`);
    for (const key of rule.absent)
      if (value[key] !== null)
        issue(key, `${value.purpose}의 ${key}는 null입니다.`);
    // [출처 4] 상태별 result·failure 조합
    const needsResult =
      value.status === 'succeeded' || value.status === 'empty';
    if (needsResult !== (value.result !== null))
      issue('result', `${value.status} 상태의 result 조합이 맞지 않습니다.`);
    if ((value.status === 'failed') !== (value.failure !== null))
      issue('failure', `${value.status} 상태의 failure 조합이 맞지 않습니다.`);
    if (value.result && value.result.kind !== value.purpose)
      issue('result', 'result.kind는 purpose와 같아야 합니다.');
  });
export type AiRequest = z.infer<typeof AiRequest>;

export const ConversationView = z
  .object({
    conversation: Conversation,
    messages: z.array(AiMessage),
    requests: z.array(AiRequest),
  })
  .strict();
export type ConversationView = z.infer<typeof ConversationView>;

// [출처 1] 202 응답: 요청 접수와 polling 위치(Location)
export type AcceptedAiRequest = { request: AiRequest; location: string | null };

async function accepted(
  path: string,
  json: unknown,
  signal?: AbortSignal,
): Promise<AcceptedAiRequest> {
  const response = await apiRequestWithResponse(path, {
    method: 'POST',
    json,
    signal,
  });
  return {
    request: success(AiRequest).parse(response.body).data,
    location: response.headers.get('Location'),
  };
}

// [출처 1, 2] POST /ai/conversations → 201 Success<Conversation>
export async function createConversation(
  body: ConversationCreate = {},
  signal?: AbortSignal,
) {
  const response = await apiRequest('/ai/conversations', {
    method: 'POST',
    json: ConversationCreate.parse(body),
    signal,
  });
  return success(Conversation).parse(response).data;
}

// [출처 1, 2] GET /ai/conversations/{conversationId} → 200 Success<ConversationView>
export async function getConversation(
  conversationId: string,
  signal?: AbortSignal,
) {
  return success(ConversationView).parse(
    await apiRequest(
      `/ai/conversations/${encodeURIComponent(conversationId)}`,
      {
        signal,
      },
    ),
  ).data;
}

// [출처 1, 2] POST /ai/conversations/{conversationId}/messages → 202 Success<AiRequest>, Location
export function sendMessage(
  conversationId: string,
  body: MessageCreate,
  signal?: AbortSignal,
) {
  return accepted(
    `/ai/conversations/${encodeURIComponent(conversationId)}/messages`,
    MessageCreate.parse(body),
    signal,
  );
}

// [출처 1, 4] GET /ai/requests/{requestId} → 200 Success<AiRequest>
export async function getAiRequest(requestId: string, signal?: AbortSignal) {
  return success(AiRequest).parse(
    await apiRequest(`/ai/requests/${encodeURIComponent(requestId)}`, {
      signal,
    }),
  ).data;
}

// [출처 1, 3] POST /ai/requests/{requestId}/retries → 202 Success<AiRequest>, Location
export function retryAiRequest(
  requestId: string,
  body: AiRetry,
  signal?: AbortSignal,
) {
  return accepted(
    `/ai/requests/${encodeURIComponent(requestId)}/retries`,
    AiRetry.parse(body),
    signal,
  );
}

// [출처 1, 3] PUT /ai/requests/{requestId}/cancellation → 200 Success<AiRequest>
export async function cancelAiRequest(
  requestId: string,
  body: AiCancel,
  signal?: AbortSignal,
) {
  const response = await apiRequest(
    `/ai/requests/${encodeURIComponent(requestId)}/cancellation`,
    { method: 'PUT', json: AiCancel.parse(body), signal },
  );
  return success(AiRequest).parse(response).data;
}

// [출처 5] POST /applications/{applicationId}/ai-reviews → 202 Success<AiRequest>, 본문 없음
export async function requestApplicantReview(
  applicationId: string,
  signal?: AbortSignal,
): Promise<AcceptedAiRequest> {
  const response = await apiRequestWithResponse(
    `/applications/${encodeURIComponent(applicationId)}/ai-reviews`,
    { method: 'POST', signal },
  );
  return {
    request: success(AiRequest).parse(response.body).data,
    location: response.headers.get('Location'),
  };
}

// [출처 5] GET /applications/{applicationId}/ai-review → 200 Success<AiRequest>, 결과·권한 없으면 404
export async function getApplicantReview(
  applicationId: string,
  signal?: AbortSignal,
) {
  return success(AiRequest).parse(
    await apiRequest(
      `/applications/${encodeURIComponent(applicationId)}/ai-review`,
      { signal },
    ),
  ).data;
}

// [출처 5] POST /teams/{teamId}/applicant-recommendations → 202 Success<AiRequest>, 본문 없음
export async function requestApplicantRecommendations(
  teamId: string,
  signal?: AbortSignal,
): Promise<AcceptedAiRequest> {
  const response = await apiRequestWithResponse(
    `/teams/${encodeURIComponent(teamId)}/applicant-recommendations`,
    { method: 'POST', signal },
  );
  return {
    request: success(AiRequest).parse(response.body).data,
    location: response.headers.get('Location'),
  };
}
