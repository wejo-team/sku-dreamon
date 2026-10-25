/**
 * [참조 출처]
 * 1. docs/api/contests.md#endpoints - GET /contests → Page<ContestSummary>, GET /contests/{contestId} → Success<Contest>
 * 2. docs/api/contests.md#queries - page, pageSize, q, fieldCode, sort(created_desc|deadline_asc), registrationStatus
 * 3. docs/api/contests.md#values - RegistrationStatus, AudienceCode
 * 4. docs/api/contests.md#contest-summary - ContestSummary 필드
 * 5. docs/api/contests.md#contest - Contest = ContestSummary 전체 + 상세 필드
 * 6. docs/api/contests.md#participation-capacity - ParticipationCapacity 조합 규칙
 * 7. docs/api/contests.md#contest-timing, #deadline-interpretation - ContestTiming, DeadlineInterpretation
 */

import { z } from 'zod';
import { apiRequest, withQuery } from '@/lib/api';
import {
  CatalogCode,
  DateString,
  HttpUrl,
  Id,
  PositiveBigInt,
  SafeInteger,
  Timestamp,
  Version,
  page,
  success,
  uniqueCodes,
} from '@/lib/api-contract';

// [출처 3]
export const RegistrationStatus = z.enum(['scheduled', 'open', 'closed']);
export type RegistrationStatus = z.infer<typeof RegistrationStatus>;
export const AudienceCode = z.enum([
  'student',
  'general',
  'unrestricted',
  'unknown',
]);
export type AudienceCode = z.infer<typeof AudienceCode>;

// [출처 4] 목록 카드
export const ContestSummary = z
  .object({
    id: Id,
    title: z.string(),
    organizer: z.string(),
    fieldCodes: uniqueCodes(z.array(CatalogCode).max(3)),
    posterUrl: HttpUrl.nullable(),
    registrationStatus: RegistrationStatus,
    startsAt: Timestamp,
    endsAt: Timestamp,
    teamCount: SafeInteger,
    isDemo: z.boolean(),
    createdAt: Timestamp,
    version: Version,
  })
  .strict();
export type ContestSummary = z.infer<typeof ContestSummary>;

// [출처 6] kind별 최소·최대 조합
export const ParticipationCapacity = z
  .object({
    kind: z.enum(['range', 'unlimited', 'unknown']),
    minimumMembers: PositiveBigInt.nullable(),
    maximumMembers: PositiveBigInt.nullable(),
  })
  .strict()
  .superRefine((value, ctx) => {
    const issue = (message: string) =>
      ctx.addIssue({ code: z.ZodIssueCode.custom, message });
    if (value.kind === 'range') {
      if (!value.minimumMembers || !value.maximumMembers)
        return issue('range는 최소·최대가 모두 필요합니다.');
      if (BigInt(value.minimumMembers) > BigInt(value.maximumMembers))
        issue('최소는 최대보다 클 수 없습니다.');
    } else if (value.kind === 'unlimited') {
      if (value.maximumMembers !== null)
        issue('unlimited의 maximumMembers는 null입니다.');
    } else if (value.minimumMembers !== null || value.maximumMembers !== null) {
      issue('unknown은 최소·최대가 모두 null입니다.');
    }
  });
export type ParticipationCapacity = z.infer<typeof ParticipationCapacity>;

// [출처 7] 마감 원문과 서비스 보완 여부
export const DeadlineInterpretation = z
  .object({
    sourceDate: DateString,
    sourceTime: z.string().nullable(),
    sourceTimeZone: z.string().nullable(),
    effectiveTimeZone: z.string(),
    timeDefaulted: z.boolean(),
    timeZoneDefaulted: z.boolean(),
  })
  .strict();
export type DeadlineInterpretation = z.infer<typeof DeadlineInterpretation>;

// [출처 7] 접수 일정
export const ContestTiming = z
  .object({
    startsAt: Timestamp,
    endsAt: Timestamp,
    openSourceDate: DateString,
    openSourceTime: z.string().nullable(),
    openSourceTimeZone: z.string().nullable(),
    openEffectiveTimeZone: z.string(),
    openTimeZoneDefaulted: z.boolean(),
    closing: DeadlineInterpretation,
  })
  .strict();
export type ContestTiming = z.infer<typeof ContestTiming>;

// [출처 5] audienceCodes: 1~2개, student+general만 함께 가능
export const Contest = ContestSummary.extend({
  description: z.string().nullable(),
  audienceCodes: z
    .array(AudienceCode)
    .min(1)
    .max(2)
    .refine(
      (codes) =>
        codes.length === 1 ||
        (codes.includes('student') && codes.includes('general')),
      'unrestricted·unknown은 단독 값입니다.',
    ),
  eligibilityText: z.string(),
  capacity: ParticipationCapacity,
  timing: ContestTiming,
  deliverables: z.string().nullable(),
  awards: z.string().nullable(),
  contact: z.string().nullable(),
  verifiedAt: Timestamp,
  sourceUrl: HttpUrl,
})
  .strict()
  // [출처 7] timing.startsAt·endsAt은 상위 Contest의 같은 이름 필드와 같은 경계
  .refine(
    (value) =>
      value.timing.startsAt === value.startsAt &&
      value.timing.endsAt === value.endsAt,
    { path: ['timing'], message: '접수 일정 경계가 상위 값과 다릅니다.' },
  );
export type Contest = z.infer<typeof Contest>;

// [출처 2] 목록 조건. 모두 선택 입력
export type ContestListQuery = {
  page?: number;
  pageSize?: number;
  q?: string;
  fieldCode?: string;
  sort?: 'created_desc' | 'deadline_asc';
  registrationStatus?: RegistrationStatus;
};

// [출처 1, 2] GET /contests → 200 Page<ContestSummary>
export async function listContests(
  query: ContestListQuery = {},
  signal?: AbortSignal,
) {
  return page(ContestSummary).parse(
    await apiRequest(withQuery('/contests', query), { signal }),
  );
}

// [출처 1, 5] GET /contests/{contestId} → 200 Success<Contest>, 없으면 404
export async function getContest(contestId: string, signal?: AbortSignal) {
  return success(Contest).parse(
    await apiRequest(`/contests/${encodeURIComponent(contestId)}`, { signal }),
  ).data;
}
