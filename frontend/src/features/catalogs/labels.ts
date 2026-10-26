/**
 * [참조 출처]
 * 1. docs/api/catalogs.md#catalogs - 코드는 Catalogs의 displayName으로 표시, 새 선택에는 isSelectable=true만
 * 2. docs/api/catalogs.md#academic-unit - parentId로 트리 구성, 선택 항목까지의 소속 경로 표시
 * 3. docs/api/applications.md#values - ApplicationStatus 값
 * 4. docs/api/contests.md#values - AudienceCode 값
 * 5. docs/design/screens.md - 화면의 상태 문구(지원 완료·검토 중·선발·미선발·취소·폐기)
 *
 * API 응답의 코드·영문 상태를 화면 문구로 바꾸는 순수 도우미입니다.
 * 선택지는 GET /catalogs 결과를 받아 만들며(features/catalogs/queries.ts useLabels), 코드를 직접 정의하지 않습니다.
 */

import {
  catalogLabel,
  selectableItems,
  type AcademicUnit,
  type Catalogs,
} from '@/features/catalogs/api';
import type { ApplicationStatus } from '@/features/applications/api';

// [출처 1, 2] 선택지·학사 목록에서 표시 도우미를 만듭니다.
function buildLabels(catalogs: Catalogs, academicUnits: AcademicUnit[]) {
  const academicUnitById = (id: string | null) =>
    id ? academicUnits.find((unit) => unit.id === id) : undefined;
  const labels = {
    catalogs,
    academicUnits,
    fieldLabel: (code: string) => catalogLabel(catalogs.fields, code),
    roleLabel: (code: string) => catalogLabel(catalogs.roles, code),
    skillLabel: (code: string) => catalogLabel(catalogs.skills, code),
    academicStatusLabel: (code: string) =>
      catalogLabel(catalogs.academicStatuses, code),
    gradeLabel: (code: string) => catalogLabel(catalogs.grades, code),
    weeklyAvailabilityLabel: (code: string) =>
      catalogLabel(catalogs.weeklyAvailabilityRanges, code),
    fieldOptions: selectableItems(catalogs.fields),
    roleOptions: selectableItems(catalogs.roles),
    skillOptions: selectableItems(catalogs.skills),
    academicStatusOptions: selectableItems(catalogs.academicStatuses),
    gradeOptions: selectableItems(catalogs.grades),
    weeklyAvailabilityOptions: selectableItems(
      catalogs.weeklyAvailabilityRanges,
    ),
    avatarPresets: catalogs.avatarPresets,
    academicUnitById,
    academicChildren: (parentId: string | null) =>
      academicUnits.filter((unit) => unit.parentId === parentId),
    // [출처 2] 선택한 항목부터 루트까지 올라가 [단과대학, 학부·학과, 전공] 순서의 경로
    academicPath: (id: string | null): AcademicUnit[] => {
      const path: AcademicUnit[] = [];
      let current = academicUnitById(id);
      while (current) {
        path.unshift(current);
        current = academicUnitById(current.parentId);
      }
      return path;
    },
  };
  return labels;
}
export type Labels = ReturnType<typeof buildLabels>;

const cache = new WeakMap<Catalogs, WeakMap<AcademicUnit[], Labels>>();

// 같은 응답이면 같은 객체를 돌려줘 화면의 메모이제이션이 깨지지 않게 합니다.
export function createLabels(
  catalogs: Catalogs,
  academicUnits: AcademicUnit[],
): Labels {
  const byUnits = cache.get(catalogs) ?? new WeakMap<AcademicUnit[], Labels>();
  cache.set(catalogs, byUnits);
  const labels =
    byUnits.get(academicUnits) ?? buildLabels(catalogs, academicUnits);
  byUnits.set(academicUnits, labels);
  return labels;
}

// [출처 3, 5] 지원 상태 문구
export const applicationStatusLabels: Record<ApplicationStatus, string> = {
  submitted: '지원 완료',
  reviewing: '검토 중',
  selected: '선발',
  rejected: '미선발',
  canceled: '지원 취소',
  discarded: '폐기',
};

// [출처 4] AudienceCode 표시 문구
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
