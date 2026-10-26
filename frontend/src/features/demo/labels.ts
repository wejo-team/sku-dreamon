/**
 * [참조 출처]
 * 1. docs/api/catalogs.md#catalogs - 코드는 Catalogs의 displayName으로 표시, 새 선택에는 isSelectable=true만
 * 2. docs/api/catalogs.md#academic-unit - parentId로 트리 구성, 선택 항목까지의 소속 경로 표시
 * 3. docs/api/applications.md#values, docs/api/teams.md#values - ApplicationStatus·RecruitmentState 값
 * 4. docs/design/screens.md - 화면의 상태 문구(지원 완료·검토 중·선발·미선발·취소·폐기)
 *
 * 화면이 API 형태 데이터(코드·영문 상태)를 기존 한국어 문구로 표시하기 위한 도우미입니다.
 * 지금은 목업 Catalogs를 사용하며, 화면을 API에 연결할 때 GET /catalogs 결과로 바꿉니다.
 */

import {
  catalogLabel,
  selectableItems,
  type AcademicUnit,
  type CatalogItem,
} from '@/features/catalogs/api';
import type { ApplicationStatus } from '@/features/applications/api';
import {
  fixtureAcademicUnits,
  fixtureCatalogs,
} from '@/features/demo/fixtures';

// [출처 1] 목업 공통 선택지(GET /catalogs 응답과 같은 모양)
export const demoCatalogs = fixtureCatalogs();
// [출처 2] 목업 학사 목록(GET /catalogs/academic-units 응답과 같은 모양)
export const demoAcademicUnits = fixtureAcademicUnits();

// [출처 1] 코드 → 표시명
export const fieldLabel = (code: string) =>
  catalogLabel(demoCatalogs.fields, code);
export const roleLabel = (code: string) =>
  catalogLabel(demoCatalogs.roles, code);
export const skillLabel = (code: string) =>
  catalogLabel(demoCatalogs.skills, code);
export const academicStatusLabel = (code: string) =>
  catalogLabel(demoCatalogs.academicStatuses, code);
export const gradeLabel = (code: string) =>
  catalogLabel(demoCatalogs.grades, code);
export const weeklyAvailabilityLabel = (code: string) =>
  catalogLabel(demoCatalogs.weeklyAvailabilityRanges, code);

// [출처 1] 새 선택용 목록
export const fieldOptions: CatalogItem[] = selectableItems(demoCatalogs.fields);
export const roleOptions: CatalogItem[] = selectableItems(demoCatalogs.roles);
export const skillOptions: CatalogItem[] = selectableItems(demoCatalogs.skills);
export const academicStatusOptions: CatalogItem[] = selectableItems(
  demoCatalogs.academicStatuses,
);
export const gradeOptions: CatalogItem[] = selectableItems(demoCatalogs.grades);
export const weeklyAvailabilityOptions: CatalogItem[] = selectableItems(
  demoCatalogs.weeklyAvailabilityRanges,
);

// [출처 3, 4] 지원 상태 문구
export const applicationStatusLabels: Record<ApplicationStatus, string> = {
  submitted: '지원 완료',
  reviewing: '검토 중',
  selected: '선발',
  rejected: '미선발',
  canceled: '지원 취소',
  discarded: '폐기',
};

// [출처 2] 학사 트리 조회
export const academicUnitById = (
  id: string | null,
  units: AcademicUnit[] = demoAcademicUnits,
) => (id ? units.find((unit) => unit.id === id) : undefined);

export const academicChildren = (
  parentId: string | null,
  units: AcademicUnit[] = demoAcademicUnits,
) => units.filter((unit) => unit.parentId === parentId);

// [출처 2] 선택한 항목부터 루트까지 올라가 [단과대학, 학부·학과, 전공] 순서의 경로를 만듭니다.
export function academicPath(
  id: string | null,
  units: AcademicUnit[] = demoAcademicUnits,
): AcademicUnit[] {
  const path: AcademicUnit[] = [];
  let current = academicUnitById(id, units);
  while (current) {
    path.unshift(current);
    current = academicUnitById(current.parentId, units);
  }
  return path;
}

// docs/api/contests.md#values AudienceCode 표시 문구
export const audienceLabels: Record<
  'student' | 'general' | 'unrestricted' | 'unknown',
  string
> = {
  student: '대학생',
  general: '일반인',
  unrestricted: '제한 없음',
  unknown: '미확인',
};

// UTC 시각을 한국시간 날짜(YYYY-MM-DD)로 표시
export const koreanDate = (timestamp: string) =>
  new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(Date.parse(timestamp));
