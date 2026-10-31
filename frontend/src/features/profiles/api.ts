/**
 * [참조 출처]
 * 1. docs/api/profiles.md#profile-endpoints - GET/PUT /me/profile, PUT /me/profile/visibility, 409 코드
 * 2. docs/api/profiles.md#profile - Profile 서버 필드 accountId·version·isPublic·isDemo·updatedAt
 * 3. docs/api/profiles.md#profile-fields - 공통 편집 필드 13개
 * 4. docs/api/profiles.md#experience - ExperienceState와 본문 조합
 * 5. docs/api/profiles.md#portfolio - Portfolio { url, title }
 * 6. docs/api/profiles.md#profile-write, #visibility-write - ProfileWrite(13개 + expectedVersion), VisibilityWrite
 * 7. docs/api/profiles.md#directory-endpoints, #person-summary - GET /people, GET /people/{accountId}, PersonSummary
 */

import { z } from 'zod';
import { CourseSummary } from '@/features/catalogs/api';
import { ApiError, apiRequest, withQuery } from '@/lib/api';
import {
  CatalogCode,
  HttpUrl,
  Id,
  NonnegativeBigInt,
  PositiveBigInt,
  Timestamp,
  Version,
  page,
  success,
  trimmedText,
} from '@/lib/api-contract';

const unique = (codes: string[]) => new Set(codes).size === codes.length;
const codeList = (min: number, max?: number) => {
  let schema = z.array(CatalogCode).min(min);
  if (max !== undefined) schema = schema.max(max);
  return schema.refine(unique, '중복 코드는 허용하지 않습니다.');
};

// [출처 4]
export const ExperienceState = z.enum(['unspecified', 'none', 'provided']);
export type ExperienceState = z.infer<typeof ExperienceState>;

// [출처 5] 객체가 있으면 두 키 모두 포함. 제거는 portfolio: null
export const Portfolio = z
  .object({ url: HttpUrl, title: trimmedText(0, 50).nullable() })
  .strict();
export type Portfolio = z.infer<typeof Portfolio>;

// [출처 3] 13개 키. 선택 입력도 키를 생략하지 않고 null 또는 []
export const profileFields = {
  realName: trimmedText(1, 50),
  profileImageCode: CatalogCode.nullable(),
  academicStatusCode: CatalogCode.nullable(),
  gradeCode: CatalogCode.nullable(),
  weeklyAvailabilityCode: CatalogCode.nullable(),
  academicUnitId: PositiveBigInt.nullable(),
  experienceState: ExperienceState,
  experienceBody: trimmedText(0, 500).nullable(),
  introduction: trimmedText(0, 300).nullable(),
  fieldCodes: codeList(1, 3),
  roleCodes: codeList(1, 2),
  skillCodes: codeList(0),
  portfolio: Portfolio.nullable(),
};

// [출처 4] 응답의 상태와 본문 조합: unspecified·none은 null, provided는 비어 있지 않은 본문
const experienceCombination = (
  value: { experienceState: ExperienceState; experienceBody: string | null },
  ctx: z.RefinementCtx,
) => {
  const provided = value.experienceState === 'provided';
  const hasBody = !!value.experienceBody?.trim();
  if (provided !== hasBody)
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      path: ['experienceBody'],
      message: 'experienceState와 experienceBody 조합이 맞지 않습니다.',
    });
};

// [출처 2, 3] 전체 현재 프로필
export const Profile = z
  .object({
    accountId: Id,
    version: Version,
    isPublic: z.boolean(),
    isDemo: z.boolean(),
    updatedAt: Timestamp,
    ...profileFields,
    // 구버전 서버의 필드 부재는 선택 이력이 비어 있는 응답과 구분합니다.
    courses: z.array(CourseSummary).optional(),
  })
  .strict()
  .superRefine(experienceCombination);
export type Profile = z.infer<typeof Profile>;

// [출처 6] 공통 필드·courseCodes·expectedVersion. 최초 저장은 "0"이며 과목 코드 생략은 기존 선택 유지.
export const ProfileWrite = z
  .object({
    expectedVersion: NonnegativeBigInt,
    ...profileFields,
    courseCodes: codeList(0).optional(),
  })
  .strict();
export type ProfileWrite = z.infer<typeof ProfileWrite>;

// 구버전 서버만 거절하는 최상위 과목 필드 오류를 일반 입력 오류와 구분합니다.
export function isCourseFeatureUnavailable(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.status === 422 &&
    error.issues.some(
      (issue) =>
        issue.type === 'extra_forbidden' &&
        issue.loc.length === 2 &&
        issue.loc[0] === 'body' &&
        issue.loc[1] === 'courseCodes',
    )
  );
}

// [출처 6] 확인 팝업에서 결정한 공개 상태
export const VisibilityWrite = z
  .object({ expectedVersion: Version, isPublic: z.boolean() })
  .strict();
export type VisibilityWrite = z.infer<typeof VisibilityWrite>;

// [출처 7] 공개 사람 카드
export const PersonSummary = z
  .object({
    accountId: Id,
    realName: trimmedText(1, 50),
    isDemo: z.boolean(),
    profileImageCode: CatalogCode.nullable(),
    introduction: trimmedText(0, 300).nullable(),
    fieldCodes: codeList(1, 3),
    roleCodes: codeList(1, 2),
    skillCodes: codeList(0),
  })
  .strict();
export type PersonSummary = z.infer<typeof PersonSummary>;

// [출처 7] 사람 목록 조건
export type PeopleQuery = {
  q?: string;
  fieldCode?: string;
  roleCode?: string;
  page?: number;
  pageSize?: number;
};

// [출처 1] GET /me/profile → 200 Success<Profile>, 미저장은 404
export async function getMyProfile(signal?: AbortSignal) {
  return success(Profile).parse(await apiRequest('/me/profile', { signal }))
    .data;
}

// [출처 1, 6] PUT /me/profile → 최초·수정 모두 200 Success<Profile>
export async function putMyProfile(body: ProfileWrite, signal?: AbortSignal) {
  const response = await apiRequest('/me/profile', {
    method: 'PUT',
    json: ProfileWrite.parse(body),
    signal,
  });
  return success(Profile).parse(response).data;
}

// [출처 1, 6] PUT /me/profile/visibility → 200 Success<Profile>
export async function putMyProfileVisibility(
  body: VisibilityWrite,
  signal?: AbortSignal,
) {
  const response = await apiRequest('/me/profile/visibility', {
    method: 'PUT',
    json: VisibilityWrite.parse(body),
    signal,
  });
  return success(Profile).parse(response).data;
}

// [출처 7] GET /people → 200 Page<PersonSummary>. 현재 공개 프로필만
export async function listPeople(
  query: PeopleQuery = {},
  signal?: AbortSignal,
) {
  return page(PersonSummary).parse(
    await apiRequest(withQuery('/people', query), { signal }),
  );
}

// [출처 7] GET /people/{accountId} → 200 Success<Profile>. 비공개·미존재는 같은 404
export async function getPerson(accountId: string, signal?: AbortSignal) {
  return success(Profile).parse(
    await apiRequest(`/people/${encodeURIComponent(accountId)}`, { signal }),
  ).data;
}
