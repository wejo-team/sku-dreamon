/**
 * [참조 출처]
 * 1. docs/api/profiles.md#profile-fields - 공통 편집 필드와 수강 과목, 선택 입력은 null 또는 []
 * 2. docs/api/profiles.md#experience - 상태·본문 정규화(provided인데 본문이 비면 unspecified·null)
 * 3. docs/api/profiles.md#portfolio - URL 제거는 portfolio: null, 제목은 선택
 * 4. docs/api/catalogs.md#academic-unit - 가장 깊게 선택한 항목 ID를 academicUnitId로 저장
 * 5. docs/specs/profile.md#input-validation - 앞뒤 공백 제거 후 검증·저장
 * 6. docs/api/profiles.md#profile-write - PUT /me/profile 본문과 courseCodes(빈 배열은 전체 제거)
 *
 * 프로필 편집 폼의 입력값과 Profile DTO·ProfileWrite 사이의 변환입니다. 폼은 선택 안 함을 빈 문자열로 다루고,
 * 저장할 때 계약에 맞게 null·[]로 바꿉니다.
 */

import type {
  ExperienceState,
  Profile,
  ProfileWrite,
} from '@/features/profiles/api';
import type { Labels } from '@/features/catalogs/labels';
import type { CourseSummary } from '@/features/catalogs/api';
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
  courses: CourseSummary[];
  portfolioUrl: string;
  portfolioTitle: string;
};

export function toFormValues(
  profile: Profile,
  academicPath: Labels['academicPath'],
): ProfileFormValues {
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
    courses: [...profile.courses],
    portfolioUrl: profile.portfolio?.url ?? '',
    portfolioTitle: profile.portfolio?.title ?? '',
  };
}

const orNull = (value: string) => value.trim() || null;

// [출처 1~6] 폼 값 → PUT /me/profile 본문. 아직 프로필이 없으면 expectedVersion "0"
export function toProfileWrite(
  values: ProfileFormValues,
  current: Pick<Profile, 'version'> | null,
): ProfileWrite {
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
    expectedVersion: current?.version ?? '0',
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
    courseCodes: values.courses.map((course) => course.code),
    portfolio: url ? { url, title: orNull(values.portfolioTitle) } : null,
  };
}
