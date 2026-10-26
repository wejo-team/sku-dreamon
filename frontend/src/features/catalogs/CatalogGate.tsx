/**
 * [참조 출처]
 * 1. docs/api/catalogs.md#catalog-endpoints - GET /catalogs, GET /catalogs/academic-units (공개)
 * 2. docs/development/frontend.md - 「API와 query」 각 화면은 로딩·오류 상태 제공
 *
 * 모든 화면이 코드 표시명·선택지에 쓰는 공통 선택지를 먼저 받은 뒤 화면을 그립니다.
 */

import type { ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/common/CommonUi';
import { useCatalogQueries } from '@/features/catalogs/queries';

// [출처 1, 2] 선택지를 받기 전에는 대기, 실패하면 다시 시도 안내
export function CatalogGate({ children }: { children: ReactNode }) {
  const { catalogs, academicUnits } = useCatalogQueries();
  if (catalogs.isError || academicUnits.isError)
    return (
      <EmptyState
        title="서비스 정보를 불러오지 못했어요"
        description="네트워크 연결을 확인한 뒤 다시 시도해 주세요."
      >
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void catalogs.refetch();
            void academicUnits.refetch();
          }}
        >
          다시 시도
        </Button>
      </EmptyState>
    );
  if (!catalogs.data || !academicUnits.data)
    return (
      <p className="preview-muted" role="status">
        불러오는 중…
      </p>
    );
  return children;
}
