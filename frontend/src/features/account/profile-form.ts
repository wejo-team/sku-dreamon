/**
 * [참조 출처]
 * 1. docs/api/profiles.md#profile-fields - 공통 편집 필드 13개, 선택 입력은 null 또는 []
 * 2. docs/api/profiles.md#experience - 상태·본문 정규화(provided인데 본문이 비면 unspecified·null)
 * 3. docs/api/profiles.md#portfolio - URL 제거는 portfolio: null, 제목은 선택
 * 4. docs/api/catalogs.md#academic-unit - 가장 깊게 선택한 항목 ID를 academicUnitId로 저장
 * 5. docs/specs/profile.md#input-validation - 앞뒤 공백 제거 후 검증·저장
 *
 * 프로필 편집 폼의 입력값과 Profile DTO 사이의 변환입니다. 폼은 선택 안 함을 빈 문자열로 다루고,
 * 저장할 때 계약에 맞게 null·[]로 바꿉니다.
 */

import type { ExperienceState, Profile } from '@/features/profiles/api';
import { academicPath } from '@/features/demo/labels';
import { normalizeWebUrl } from '@/features/demo/profile-fields';

export type ProfileFormValues = {
  realName: string;
  profileImageCode: string | null;
  academicStatusCode: string;
  gradeCode: string;
  /** [출처 4] 단과대학 → 학부·학과 → 전공 계층별 선택 ID */
  collegeId: string;
  departmentId: string;
  majorId: string;
  weeklyAvailabilityCode: string;
  experienceState: ExperienceState;
  experienceBody: string;
  introduction: string;
  fieldCodes: string[];
  roleCodes: string[];
  skillCodes: string[];
  portfolioUrl: string;
  portfolioTitle: string;
};

export function toFormValues(profile: Profile): ProfileFormValues {
  const [college, department, major] = academicPath(profile.academicUnitId);
  return {
    realName: profile.realName,
    profileImageCode: profile.profileImageCode,
    academicStatusCode: profile.academicStatusCode ?? '',
    gradeCode: profile.gradeCode ?? '',
    collegeId: college?.id ?? '',
    departmentId: department?.id ?? '',
    majorId: major?.id ?? '',
    weeklyAvailabilityCode: profile.weeklyAvailabilityCode ?? '',
    experienceState: profile.experienceState,
    experienceBody: profile.experienceBody ?? '',
    introduction: profile.introduction ?? '',
    fieldCodes: [...profile.fieldCodes],
    roleCodes: [...profile.roleCodes],
    skillCodes: [...profile.skillCodes],
    portfolioUrl: profile.portfolio?.url ?? '',
    portfolioTitle: profile.portfolio?.title ?? '',
  };
}

const orNull = (value: string) => value.trim() || null;

// [출처 1~5] 폼 값 → 저장할 Profile. 공개 상태·소유 계정은 기존 값을 유지하고 버전을 올립니다.
export function fromFormValues(
  values: ProfileFormValues,
  current: Profile,
  now = new Date(),
): Profile {
  const experienceBody = values.experienceBody.trim();
  const experienceState: ExperienceState =
    values.experienceState === 'provided' && !experienceBody
      ? 'unspecified'
      : values.experienceState;
  // [출처 3] 검증을 통과한 주소는 정규화된 형태로 저장(공개 미리보기와 같은 링크)
  const url = values.portfolioUrl.trim()
    ? normalizeWebUrl(values.portfolioUrl.trim())
    : '';
  return {
    ...current,
    realName: values.realName.trim(),
    profileImageCode: values.profileImageCode,
    academicStatusCode: orNull(values.academicStatusCode),
    gradeCode: orNull(values.gradeCode),
    academicUnitId:
      orNull(values.majorId) ??
      orNull(values.departmentId) ??
      orNull(values.collegeId),
    weeklyAvailabilityCode: orNull(values.weeklyAvailabilityCode),
    experienceState,
    experienceBody: experienceState === 'provided' ? experienceBody : null,
    introduction: orNull(values.introduction),
    fieldCodes: [...values.fieldCodes],
    roleCodes: [...values.roleCodes],
    skillCodes: [...values.skillCodes],
    portfolio: url ? { url, title: orNull(values.portfolioTitle) } : null,
    version: (BigInt(current.version) + 1n).toString(),
    updatedAt: now.toISOString().replace(/\.\d{3}Z$/, 'Z'),
  };
}
