/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/ListPagination.tsx - 번호 페이지 원본
 * 2. docs/design/tokens.md - 현재 번호 녹색·나머지 outline, aria-current=page, 이전·최대 3개 번호·다음, 44px
 * 3. docs/design/screens.md - 「페이지 이동과 공모전별 팀 목록」 0건 숨김, 1페이지만 있을 때 비활성 이전/다음
 * 4. docs/design/assets/pagination-320.png, people-pagination-390.png - 페이지 조작 화면
 */

import { useId } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Link } from 'react-router';
import { Button } from '@/components/ui/button';

type ListPaginationProps = {
  page: number;
  totalPages: number;
  hrefForPage: (page: number) => string;
  onNavigate?: () => void;
  label?: string;
};

// [출처 2, 3, 4] URL page 값을 유지하는 번호 페이지
export function ListPagination({
  page,
  totalPages,
  hrefForPage,
  onNavigate,
  label = '페이지 선택',
}: ListPaginationProps) {
  const summaryId = useId();
  if (totalPages === 0) return null;

  const startPage = Math.max(1, Math.min(page - 1, totalPages - 2));
  const pages = Array.from(
    { length: Math.min(3, totalPages) },
    (_, index) => startPage + index,
  );

  return (
    <nav
      className="preview-pagination"
      aria-label={label}
      aria-describedby={totalPages > 1 ? summaryId : undefined}
    >
      <ul className="preview-pagination-list">
        <li>
          {page > 1 ? (
            <Button asChild variant="outline" className="preview-page-link">
              <Link
                to={hrefForPage(page - 1)}
                aria-label="이전 페이지"
                title="이전 페이지"
                onClick={onNavigate}
              >
                <ChevronLeft aria-hidden="true" />
              </Link>
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              className="preview-page-link"
              aria-label="이전 페이지"
              title="이전 페이지"
              disabled
            >
              <ChevronLeft aria-hidden="true" />
            </Button>
          )}
        </li>
        {pages.map((number) => (
          <li key={number}>
            <Button
              asChild
              variant={number === page ? 'default' : 'outline'}
              className="preview-page-link"
            >
              <Link
                to={hrefForPage(number)}
                aria-label={`${number}페이지`}
                aria-current={number === page ? 'page' : undefined}
                onClick={onNavigate}
              >
                {number}
              </Link>
            </Button>
          </li>
        ))}
        <li>
          {page < totalPages ? (
            <Button asChild variant="outline" className="preview-page-link">
              <Link
                to={hrefForPage(page + 1)}
                aria-label="다음 페이지"
                title="다음 페이지"
                onClick={onNavigate}
              >
                <ChevronRight aria-hidden="true" />
              </Link>
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              className="preview-page-link"
              aria-label="다음 페이지"
              title="다음 페이지"
              disabled
            >
              <ChevronRight aria-hidden="true" />
            </Button>
          )}
        </li>
      </ul>
      {totalPages > 1 && (
        <p id={summaryId} className="preview-pagination-summary">
          전체 {totalPages}페이지 중 {page}페이지
        </p>
      )}
    </nav>
  );
}
