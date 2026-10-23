/**
 * [참조 출처]
 * 1. docs/design/tokens.md - 페이지네이션 번호 버튼 및 최소 44px 터치 영역 규격
 * 2. docs/design/assets/pagination-320.png - 320px 모바일 화면에서의 번호 페이지 배치
 * 3. docs/development/frontend.md - URL SearchParams 기반 페이지 상태 관리(?page=N)
 * 4. design-reference/src/features/design-preview/ListPagination.tsx - ListPagination 구현 원본
 */

import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from './button';

export interface ListPaginationProps {
  page: number;
  totalItems: number;
  pageSize?: number;
  onPageChange: (newPage: number) => void;
}

// [출처 1, 2, 4] 한 줄에 이전, 최대 3개 번호, 다음 버튼만 두고 각 44x44px 이상을 확보하는 모바일 페이지네이션
export function ListPagination({
  page,
  totalItems,
  pageSize = 6,
  onPageChange,
}: ListPaginationProps) {
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize));
  if (totalPages <= 1) return null;

  // [출처 1, 4] 현재 페이지 중심 최대 3개 번호 계산
  const startPage = Math.max(
    1,
    Math.min(page - 1, totalPages - 2 > 0 ? totalPages - 2 : 1),
  );
  const endPage = Math.min(totalPages, startPage + 2);
  const pages = [];
  for (let i = startPage; i <= endPage; i++) {
    pages.push(i);
  }

  return (
    <nav
      aria-label="페이지 이동"
      className="my-4 flex items-center justify-center gap-1.5"
    >
      {/* [출처 1] 이전 페이지 버튼 (최소 44px) */}
      <Button
        variant="outline"
        disabled={page <= 1}
        onClick={() => onPageChange(page - 1)}
        aria-label="이전 페이지"
        className="size-11 p-0"
      >
        <ChevronLeft size={18} aria-hidden="true" />
      </Button>

      {/* [출처 2] 번호 버튼 (현재 페이지는 주요 녹색 강조) */}
      {pages.map((p) => (
        <Button
          key={p}
          variant={p === page ? 'default' : 'outline'}
          onClick={() => onPageChange(p)}
          aria-current={p === page ? 'page' : undefined}
          aria-label={`${p} 페이지`}
          className="size-11 font-medium"
        >
          {p}
        </Button>
      ))}

      {/* [출처 1] 다음 페이지 버튼 (최소 44px) */}
      <Button
        variant="outline"
        disabled={page >= totalPages}
        onClick={() => onPageChange(page + 1)}
        aria-label="다음 페이지"
        className="size-11 p-0"
      >
        <ChevronRight size={18} aria-hidden="true" />
      </Button>
    </nav>
  );
}
