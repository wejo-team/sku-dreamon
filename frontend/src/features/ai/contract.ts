// 서버 AI DTO의 채팅 SSE·지원자 JSON v3를 camelCase 경계에서 검증합니다.
import { z } from 'zod';
import {
  Id,
  PositiveBigInt,
  PositiveSafeInteger,
  Timestamp,
  Version,
} from '@/lib/api-contract';

const textWithin = (maximum: number) =>
  z.string().refine((value) => [...value].length <= maximum);
const message = z
  .string()
  .transform((value) => value.normalize('NFC').trim())
  .refine(
    (value) =>
      [...value].length >= 1 &&
      [...value].length <= 1000 &&
      !value.includes('\0') &&
      !/[\uD800-\uDFFF]/u.test(value),
    '메시지는 올바른 Unicode 1~1,000자여야 합니다.',
  );
export const AiPurpose = z.enum([
  'chat',
  'applicant_review',
  'applicant_recommendation',
]);
export type AiPurpose = z.infer<typeof AiPurpose>;
export const PreviousResult = z
  .object({ requestId: Id, attempt: PositiveSafeInteger })
  .strict();
export const ChatStart = z
  .object({
    requestId: Id,
    conversationId: Id,
    clientMessageId: Id,
    content: message,
    resultFormat: z.literal('rich').optional(),
    history: z.array(message).max(20).default([]),
    previousResults: z.array(PreviousResult).max(20).default([]),
  })
  .strict()
  .refine(
    (value) =>
      [...value.content].length +
        value.history.reduce((n, s) => n + [...s].length, 0) <=
      12000,
    '대화가 길어졌어요. 새 대화를 시작해 주세요.',
  );
export type ChatStart = z.infer<typeof ChatStart>;
export const TargetStart = z.object({ requestId: Id }).strict();
export type TargetStart = z.infer<typeof TargetStart>;
export const RetryStart = z
  .object({
    expectedAttempt: PositiveSafeInteger,
    input: z.union([ChatStart, TargetStart]),
  })
  .strict();
export type RetryStart = z.infer<typeof RetryStart>;
export const PersonDetails = z
  .object({
    kind: z.literal('person'),
    skillCodes: z
      .array(
        z.enum([
          'programming',
          'ui_ux',
          'data_analysis',
          'video_editing',
          'document_writing',
          'service_planning',
          'market_research',
          'graphic_design',
          'presentation_design',
          'data_visualization',
          'social_media_marketing',
          'content_planning',
          'public_speaking',
        ]),
      )
      .max(13),
    weeklyAvailabilityCode: z
      .enum(['under_5', 'from_5_to_10', 'from_10_to_20', 'at_least_20'])
      .nullable(),
    experienceState: z.enum(['unspecified', 'none', 'provided']),
    experienceBody: textWithin(500).nullable(),
    introduction: textWithin(300).nullable(),
  })
  .strict();
export type PersonDetails = z.infer<typeof PersonDetails>;

export const BasicResourceCard = z
  .object({
    kind: z.enum(['contest', 'team', 'person']),
    resourceId: Id,
    title: textWithin(500),
    reason: textWithin(500),
    fieldCodes: z.array(z.string()),
    roleCodes: z.array(z.string()),
    isDemo: z.boolean(),
  })
  .strict();
export type BasicResourceCard = z.infer<typeof BasicResourceCard>;
export const RichResourceCard = z
  .object({
    kind: z.enum(['contest', 'team', 'person']),
    resourceId: Id,
    title: textWithin(500),
    reason: textWithin(500),
    fieldCodes: z.array(z.string()),
    roleCodes: z.array(z.string()),
    isDemo: z.boolean(),
    evidence: z.array(textWithin(500)).max(6),
    details: z.discriminatedUnion('kind', [
      PersonDetails,
      z
        .object({
          kind: z.literal('team'),
          contestTitle: textWithin(500),
          capacity: PositiveBigInt,
          memberCount: PositiveSafeInteger,
          recruitmentEndsAt: Timestamp,
          isRecruiting: z.boolean(),
        })
        .strict(),
      z
        .object({
          kind: z.literal('contest'),
          organizer: textWithin(500),
          registrationStatus: z.enum(['scheduled', 'open', 'closed']),
          startsAt: Timestamp,
          endsAt: Timestamp,
        })
        .strict(),
    ]),
  })
  .strict()
  .refine((card) => card.kind === card.details.kind, {
    path: ['details', 'kind'],
    message: '카드와 상세 정보의 종류가 다릅니다.',
  });
export type RichResourceCard = z.infer<typeof RichResourceCard>;

// 두 strict 형식만 허용하고 구형 결과 필드를 임의로 보완하지 않습니다.
export const ResourceCard = z.union([RichResourceCard, BasicResourceCard]);
export type ResourceCard = z.infer<typeof ResourceCard>;
export const ChatResult = z
  .object({
    kind: z.literal('chat'),
    answer: textWithin(12000),
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
export const AssessmentInformationStatus = z.enum([
  'sufficient',
  'insufficient',
]);
export type AssessmentInformationStatus = z.infer<
  typeof AssessmentInformationStatus
>;
export const AssessmentEvidence = z
  .object({
    source: z.enum([
      'application.role',
      'application.message',
      'profile.roleCodes',
      'profile.skillCodes',
      'profile.experienceState',
      'profile.experienceBody',
      'profile.weeklyAvailabilityCode',
      'profile.introduction',
      'profile.courses',
      'team.roleCodes',
      'team.introduction',
    ]),
    text: textWithin(500).refine((value) => value.trim().length > 0),
  })
  .strict();
export const AssessmentCriterion = z
  .object({
    key: z.enum(['role', 'skills', 'experience', 'availability']),
    score: z.number().int().min(0).max(100).multipleOf(5).nullable(),
    informationStatus: AssessmentInformationStatus,
    summary: textWithin(300).refine((value) => value.trim().length > 0),
    evidence: z.array(AssessmentEvidence).max(6),
  })
  .strict()
  .refine(
    (criterion) =>
      (criterion.informationStatus === 'sufficient') ===
      (criterion.score !== null),
    {
      path: ['score'],
      message: '자료가 충분한 항목에만 점수가 필요합니다.',
    },
  )
  .refine(
    (criterion) => criterion.score === null || criterion.evidence.length > 0,
    {
      path: ['evidence'],
      message: '점수가 있는 항목에는 실제 자료가 필요합니다.',
    },
  );
export type AssessmentCriterion = z.infer<typeof AssessmentCriterion>;
export const ApplicantAssessment = z
  .object({
    criteria: z
      .array(AssessmentCriterion)
      .length(4)
      .refine(
        (criteria) => new Set(criteria.map((item) => item.key)).size === 4,
        '네 가지 검토 항목이 모두 필요합니다.',
      ),
    questions: z
      .array(textWithin(200).refine((value) => value.trim().length > 0))
      .max(3),
  })
  .strict();
export type ApplicantAssessment = z.infer<typeof ApplicantAssessment>;
export const ApplicantReviewResult = z
  .object({
    schemaVersion: z.literal(3),
    kind: z.literal('applicant_review'),
    applicationId: Id,
    summary: textWithin(600).refine((value) => value.trim().length > 0),
    assessment: ApplicantAssessment,
    evidence: z.array(textWithin(500)).max(6),
    profileVersions: z.array(ProfileVersion).length(1),
    isStale: z.boolean(),
    isSelectionCandidate: z.boolean(),
    generatedAt: Timestamp,
  })
  .strict();
export type ApplicantReviewResult = z.infer<typeof ApplicantReviewResult>;
export const ApplicantProfileFacts = z
  .object({
    skillCodes: z
      .array(
        z.enum([
          'programming',
          'ui_ux',
          'data_analysis',
          'video_editing',
          'document_writing',
          'service_planning',
          'market_research',
          'graphic_design',
          'presentation_design',
          'data_visualization',
          'social_media_marketing',
          'content_planning',
          'public_speaking',
        ]),
      )
      .max(13),
  })
  .strict();
export const ApplicantRecommendation = z
  .object({
    applicationId: Id,
    title: textWithin(500),
    reason: textWithin(500),
    profileVersion: ProfileVersion,
    assessment: ApplicantAssessment,
    profile: ApplicantProfileFacts,
  })
  .strict();
export type ApplicantRecommendation = z.infer<typeof ApplicantRecommendation>;
export const ApplicantRecommendationResult = z
  .object({
    schemaVersion: z.literal(3),
    kind: z.literal('applicant_recommendation'),
    summary: textWithin(600).refine((value) => value.trim().length > 0),
    candidates: z.array(ApplicantRecommendation).max(100),
    isStale: z.boolean(),
    generatedAt: Timestamp,
  })
  .strict();
export type ApplicantRecommendationResult = z.infer<
  typeof ApplicantRecommendationResult
>;
export const AiResult = z.discriminatedUnion('kind', [
  ChatResult,
  ApplicantReviewResult,
  ApplicantRecommendationResult,
]);
export type AiResult = z.infer<typeof AiResult>;
export const ApplicantCompletion = z
  .object({
    requestId: Id,
    attempt: PositiveSafeInteger,
    status: z.enum(['succeeded', 'empty', 'canceled', 'invalidated']),
    result: z
      .discriminatedUnion('kind', [
        ApplicantReviewResult,
        ApplicantRecommendationResult,
      ])
      .nullable(),
  })
  .strict()
  .refine(
    (value) =>
      (value.status === 'succeeded' || value.status === 'empty') ===
      (value.result !== null),
  );

export type ApplicantCompletion = z.infer<typeof ApplicantCompletion>;
export const AiFailure = z
  .object({
    code: z.enum([
      'temporary_failure',
      'invalid_output',
      'context_changed',
      'limit_exceeded',
    ]),
    message: z.string(),
    retryable: z.boolean(),
  })
  .strict();
export type AiFailure = z.infer<typeof AiFailure>;
export const AiRequestView = z
  .object({
    id: Id,
    purpose: AiPurpose,
    conversationId: Id.nullable(),
    teamId: Id.nullable(),
    applicationId: Id.nullable(),
    attempt: PositiveSafeInteger,
    status: z.enum(['pending', 'succeeded', 'empty', 'failed', 'canceled']),
    failure: AiFailure.nullable(),
    expiresAt: Timestamp,
  })
  .strict();
export type AiRequestView = z.infer<typeof AiRequestView>;
export const ResultValidation = z
  .object({ valid: z.boolean(), result: AiResult.nullable() })
  .strict()
  .refine((value) => value.valid === (value.result !== null));
export type ResultValidation = z.infer<typeof ResultValidation>;
const base = {
  requestId: Id,
  attempt: PositiveSafeInteger,
  sequence: PositiveSafeInteger,
};
export const AiEvent = z.discriminatedUnion('event', [
  z
    .object({ ...base, event: z.literal('started'), purpose: AiPurpose })
    .strict(),
  z
    .object({
      ...base,
      event: z.literal('progress'),
      stage: z.enum(['searching', 'validating', 'writing']),
    })
    .strict(),
  z
    .object({ ...base, event: z.literal('answer.delta'), text: z.string() })
    .strict(),
  z.object({ ...base, event: z.literal('result'), result: AiResult }).strict(),
  z
    .object({
      ...base,
      event: z.literal('done'),
      status: z.enum(['succeeded', 'empty']),
    })
    .strict(),
  z.object({ ...base, event: z.literal('error'), failure: AiFailure }).strict(),
  z.object({ ...base, event: z.literal('canceled') }).strict(),
  z
    .object({
      ...base,
      event: z.literal('invalidated'),
      reason: z.literal('context_changed'),
    })
    .strict(),
]);
export type AiEvent = z.infer<typeof AiEvent>;
