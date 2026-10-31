/**
 * [참조 출처]
 * 1. docs/api/catalogs.md#catalog-endpoints - GET /catalogs, GET /catalogs/academic-units (공개)
 * 2. docs/api/catalogs.md#catalogs - 코드는 displayName으로 표시, 새 선택에는 isSelectable=true만
 * 3. docs/api/catalogs.md#academic-unit - parentId로 트리 구성
 *
 * 공통 선택지는 화면 전체가 쓰는 공개 데이터라 앱 시작 때 한 번 받아 오래 보관합니다.
 */

import { queryOptions, useQuery } from '@tanstack/react-query';
import {
  getAcademicUnits,
  getCatalogs,
  listCourses,
  type CoursesQuery,
} from '@/features/catalogs/api';
import { createLabels } from '@/features/catalogs/labels';
import { queryKeys } from '@/lib/query-keys';

export const catalogsQueryOptions = queryOptions({
  queryKey: queryKeys.catalogs,
  queryFn: ({ signal }) => getCatalogs(signal),
  staleTime: Infinity,
});

export const academicUnitsQueryOptions = queryOptions({
  queryKey: queryKeys.academicUnits,
  queryFn: ({ signal }) => getAcademicUnits(signal),
  staleTime: Infinity,
});

export const coursesQueryOptions = (query: CoursesQuery) =>
  queryOptions({
    queryKey: queryKeys.courses(query),
    queryFn: ({ signal }) => listCourses(query, signal),
    staleTime: 5 * 60 * 1000,
  });

/** 선택지 두 목록의 로딩 상태(앱 시작 시 CatalogGate가 기다립니다). */
export function useCatalogQueries() {
  const catalogs = useQuery(catalogsQueryOptions);
  const academicUnits = useQuery(academicUnitsQueryOptions);
  return { catalogs, academicUnits };
}

/**
 * [출처 2, 3] 코드 → 표시명, 선택 목록, 학사 경로 도우미.
 * CatalogGate 안에서만 호출합니다(두 목록이 이미 캐시에 있음).
 */
export function useLabels() {
  const { catalogs, academicUnits } = useCatalogQueries();
  if (!catalogs.data || !academicUnits.data)
    throw new Error('useLabels는 선택지를 불러온 뒤 사용해야 합니다.');
  return createLabels(catalogs.data, academicUnits.data);
}
