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
