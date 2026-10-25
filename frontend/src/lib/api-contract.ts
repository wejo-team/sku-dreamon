/**
 * [참조 출처]
 * 1. docs/api/conventions.md#types - 공통 타입 Id·Timestamp·CatalogCode·HttpUrl·PositiveBigInt·NonnegativeBigInt·Version
 * 2. docs/api/conventions.md#success-responses - Success<T>, Page<T>
 * 3. docs/api/conventions.md#pagination - PageMeta 필드와 범위
 * 4. docs/api/conventions.md#errors - Error·ErrorDetail·ValidationError·ValidationIssue
 * 5. docs/api/conventions.md#versioned-action - VersionedAction
 * 6. docs/development/frontend.md - 「API와 query」 응답을 Zod로 검증한 뒤 같은 camelCase 이름으로 사용
 * 7. docs/api/teams.md#deadline-input - 실제 달력 날짜, IANA 시간대 또는 명시적 UTC offset
 * 8. docs/api/contests.md#contest-summary, docs/api/teams.md#team-summary - 코드 목록은 중복 없음
 * 9. docs/api/profiles.md#profile-fields - 텍스트 길이는 앞뒤 공백 제거 후 계산
 *
 * 타입 이름은 문서 표기를 그대로 따릅니다. 응답 객체는 strict로 선언하지 않은 키를 거부합니다
 * (출처 1 「선언하지 않은 객체 필드는 요청·응답 계약에 없습니다」).
 */

import { z } from 'zod';

const MAX_BIGINT = 9223372036854775807n;
const MAX_SAFE = 9007199254740991;

// [출처 1] UUID 문자열. 특정 생성 버전을 전제하지 않습니다.
export const Id = z
  .string()
  .regex(
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i,
    'UUID 문자열이어야 합니다.',
  );

// [출처 1] UTC ISO 8601, 끝은 Z
export const Timestamp = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?Z$/)
  .refine(
    (value) => !Number.isNaN(Date.parse(value)),
    '유효한 시각이 아닙니다.',
  );

// [출처 1] 길이 1~64의 카탈로그 코드
export const CatalogCode = z.string().min(1).max(64);

// [출처 1] http:// 또는 https://로 시작하는 유효한 절대 URL
export const HttpUrl = z.string().refine((value) => {
  if (!/^https?:\/\//i.test(value)) return false;
  try {
    new URL(value);
    return true;
  } catch {
    return false;
  }
}, 'http:// 또는 https:// 절대 URL이어야 합니다.');

const decimal = (min: bigint) =>
  z.string().refine((value) => {
    if (!/^(0|[1-9]\d*)$/.test(value)) return false;
    const number = BigInt(value);
    return number >= min && number <= MAX_BIGINT;
  }, '십진 문자열 범위를 벗어났습니다.');

// [출처 1] 1~9223372036854775807의 십진 문자열. 부호·소수점·선행 0 없음
export const PositiveBigInt = decimal(1n);
// [출처 1] PositiveBigInt 또는 "0"
export const NonnegativeBigInt = decimal(0n);
// [출처 1] 리소스 변경 버전
export const Version = PositiveBigInt;

// [출처 1] 개수·페이지 등 JSON 안전 정수
export const SafeInteger = z.number().int().min(0).max(MAX_SAFE);
export const PositiveSafeInteger = z.number().int().min(1).max(MAX_SAFE);

// [출처 3] 번호 페이지 정보. 모든 필드 필수·NULL 불가
export const PageMeta = z
  .object({
    page: PositiveSafeInteger,
    pageSize: z.number().int().min(1).max(100),
    total: SafeInteger,
    totalPages: SafeInteger,
  })
  .strict();
export type PageMeta = z.infer<typeof PageMeta>;

// [출처 2] { data: T }. 현재 제품 API에서 data는 null 불가
export const success = <T extends z.ZodTypeAny>(data: T) =>
  z.object({ data }).strict();

// [출처 2, 3] { data: T[], pagination: PageMeta }
export const page = <T extends z.ZodTypeAny>(item: T) =>
  z.object({ data: z.array(item), pagination: PageMeta }).strict();

export type Page<T> = { data: T[]; pagination: PageMeta };

// [출처 5] 상태 변경 요청 본문 { expectedVersion }
export const VersionedAction = z.object({ expectedVersion: Version }).strict();
export type VersionedAction = z.infer<typeof VersionedAction>;

// [출처 4] 업무 오류 본문
export const ErrorDetail = z.object({ code: z.string(), message: z.string() });
export const errorSchema = z.object({
  error: ErrorDetail,
  requestId: z.string(),
});
export type ApiErrorBody = z.infer<typeof errorSchema>;

// [출처 4] FastAPI 호환 422 본문
export const ValidationIssue = z.object({
  loc: z.array(z.union([z.string(), z.number().int()])),
  msg: z.string(),
  type: z.string(),
});
export type ValidationIssue = z.infer<typeof ValidationIssue>;
export const validationErrorSchema = z.object({
  detail: z.array(ValidationIssue).min(1),
});

// [출처 6] 응답을 계약 스키마로 검증합니다. 실패하면 ZodError를 던져 화면이 잘못된 데이터를 쓰지 않게 합니다.
export function parseWith<T extends z.ZodTypeAny>(
  schema: T,
  body: unknown,
): z.infer<T> {
  return schema.parse(body);
}

// [출처 7] 날짜(YYYY-MM-DD) 문자열. 2026-02-30처럼 달력에 없는 날짜는 거부합니다.
export const DateString = z
  .string()
  .regex(/^\d{4}-\d{2}-\d{2}$/)
  .refine((value) => {
    const [year, month, day] = value.split('-').map(Number) as [
      number,
      number,
      number,
    ];
    const date = new Date(Date.UTC(year, month - 1, day));
    return (
      date.getUTCFullYear() === year &&
      date.getUTCMonth() === month - 1 &&
      date.getUTCDate() === day
    );
  }, '실제 달력 날짜여야 합니다.');

// [출처 7] IANA 시간대(예: Asia/Seoul) 또는 명시적 UTC offset(예: +09:00, Z)
export const TimeZoneName = z.string().refine((value) => {
  if (/^(Z|UTC|[+-](0\d|1[0-4]):[0-5]\d)$/.test(value)) return true;
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: value });
    return value.includes('/');
  } catch {
    return false;
  }
}, 'IANA 시간대 또는 UTC offset이어야 합니다.');

// [출처 8] 중복 없는 코드 배열
export const uniqueCodes = (schema: z.ZodArray<z.ZodString>) =>
  schema.refine(
    (items) => new Set(items).size === items.length,
    '중복 없이 선택해야 합니다.',
  );

// [출처 9] 앞뒤 공백 제거 후 길이를 검사하는 텍스트(코드포인트 기준). 원문은 그대로 둡니다.
export const trimmedText = (min: number, max: number) =>
  z.string().refine((value) => {
    const length = [...value.trim()].length;
    return length >= min && length <= max;
  }, `앞뒤 공백 제거 후 ${min}~${max}자여야 합니다.`);
