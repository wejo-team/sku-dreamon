/**
 * [참조 출처]
 * 1. docs/api/catalogs.md#catalog-endpoints - GET /catalogs, GET /catalogs/academic-units
 * 2. docs/api/catalogs.md#catalog-item - CatalogItem { code, displayName, isSelectable, sortOrder }, AvatarPreset(+assetUrl)
 * 3. docs/api/catalogs.md#catalogs - Catalogs 일곱 목록, 각 목록은 sortOrder ASC, code ASC
 * 4. docs/api/catalogs.md#academic-unit - AcademicUnit { id, name, parentId, isSelectable }
 */

import { z } from 'zod';
import { apiRequest, withQuery } from '@/lib/api';
import {
  CatalogCode,
  HttpUrl,
  PositiveBigInt,
  page,
  success,
} from '@/lib/api-contract';

const int32 = z.number().int().min(-2147483648).max(2147483647);

// [출처 2]
export const CatalogItem = z
  .object({
    code: CatalogCode,
    displayName: z.string(),
    isSelectable: z.boolean(),
    sortOrder: int32,
  })
  .strict();
export type CatalogItem = z.infer<typeof CatalogItem>;

// [출처 2] CatalogItem 네 필드 + 필수 assetUrl
export const AvatarPreset = CatalogItem.extend({ assetUrl: HttpUrl }).strict();
export type AvatarPreset = z.infer<typeof AvatarPreset>;

// [출처 3]
export const Catalogs = z
  .object({
    fields: z.array(CatalogItem),
    roles: z.array(CatalogItem),
    skills: z.array(CatalogItem),
    academicStatuses: z.array(CatalogItem),
    grades: z.array(CatalogItem),
    weeklyAvailabilityRanges: z.array(CatalogItem),
    avatarPresets: z.array(AvatarPreset),
  })
  .strict();
export type Catalogs = z.infer<typeof Catalogs>;

// [출처 4] id·parentId는 십진 문자열. 단과대학 루트의 parentId는 null
export const AcademicUnit = z
  .object({
    id: PositiveBigInt,
    name: z.string().min(1).max(100),
    parentId: PositiveBigInt.nullable(),
    isSelectable: z.boolean(),
  })
  .strict();
export type AcademicUnit = z.infer<typeof AcademicUnit>;

// 수강과목은 학수번호로 식별하며 연도·분반을 구분하지 않습니다.
export const CourseSummary = z
  .object({ code: CatalogCode, name: z.string().min(1) })
  .strict();
export type CourseSummary = z.infer<typeof CourseSummary>;
export const Course = CourseSummary.extend({
  aliases: z.array(z.string()),
  departments: z.array(z.string()),
}).strict();
export type Course = z.infer<typeof Course>;
export type CoursesQuery = { q?: string; page?: number; pageSize?: number };

export async function listCourses(
  query: CoursesQuery = {},
  signal?: AbortSignal,
) {
  return page(Course).parse(
    await apiRequest(withQuery('/catalogs/courses', query), { signal }),
  );
}

// [출처 1] GET /catalogs → 200 Success<Catalogs>
export async function getCatalogs(signal?: AbortSignal) {
  return success(Catalogs).parse(await apiRequest('/catalogs', { signal }))
    .data;
}

// [출처 1, 4] GET /catalogs/academic-units → 200 Success<AcademicUnit[]>
export async function getAcademicUnits(signal?: AbortSignal) {
  return success(z.array(AcademicUnit)).parse(
    await apiRequest('/catalogs/academic-units', { signal }),
  ).data;
}

// [출처 3] 코드 → 표시명. 목록에 없는 코드는 코드 그대로 보여 데이터 누락을 숨기지 않습니다.
export function catalogLabel(items: CatalogItem[], code: string) {
  return items.find((item) => item.code === code)?.displayName ?? code;
}

// [출처 3] 새 선택에는 isSelectable=true만 사용합니다.
export function selectableItems<T extends CatalogItem>(items: T[]) {
  return items.filter((item) => item.isSelectable);
}
