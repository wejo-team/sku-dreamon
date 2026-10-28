/**
 * 처음 이동과 최대 5개 페이지 번호를 한 줄로 표시하는 공통 페이지 이동.
 * docs/design/tokens.md, docs/design/screens.md의 44px 조작 영역을 유지한다.
 */

import { useId } from 'react';
import { Link } from 'react-router';
import { Button } from '@/components/ui/button';

type ListPaginationProps = {
  page: number;
  totalPages: number;
  hrefForPage: (page: number) => string;
  onNavigate?: () => void;
  label?: string;
};

export function ListPagination({
  page,
  totalPages,
  hrefForPage,
  onNavigate,
  label = '페이지 선택',
}: ListPaginationProps) {
  const summaryId = useId();
  if (totalPages === 0) return null;

  const startPage = Math.max(1, Math.min(page - 2, totalPages - 4));
  const pages = Array.from(
    { length: Math.min(5, totalPages) },
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
          {page <= 1 ? (
            <Button
              type="button"
              variant="outline"
              className="preview-page-link"
              aria-label="처음 페이지"
              disabled
            >
              처음
            </Button>
          ) : (
            <Button asChild variant="outline" className="preview-page-link">
              <Link
                to={hrefForPage(1)}
                aria-label="처음 페이지"
                onClick={onNavigate}
              >
                처음
              </Link>
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
      </ul>
      {totalPages > 1 && (
        <p id={summaryId} className="preview-pagination-summary">
          전체 {totalPages}페이지 중 {page}페이지
        </p>
      )}
    </nav>
  );
}
