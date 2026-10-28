// 서버 AI DTO의 요청·결과·SSE 이벤트를 camelCase 경계에서 검증합니다.
import { z } from 'zod';
import {
  Id,
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
export const ResourceCard = z
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
export const ApplicantReviewResult = z
  .object({
    kind: z.literal('applicant_review'),
    applicationId: Id,
    summary: textWithin(12000),
    evidence: z.array(textWithin(500)).max(6),
    profileVersions: z.array(ProfileVersion).length(1),
    isStale: z.boolean(),
    isSelectionCandidate: z.boolean(),
    generatedAt: Timestamp,
  })
  .strict();
export type ApplicantReviewResult = z.infer<typeof ApplicantReviewResult>;
export const ApplicantRecommendationResult = z
  .object({
    kind: z.literal('applicant_recommendation'),
    summary: textWithin(12000),
    candidates: z
      .array(
        z
          .object({
            applicationId: Id,
            reason: textWithin(500),
            profileVersion: ProfileVersion,
          })
          .strict(),
      )
      .max(100),
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
