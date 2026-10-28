/**
 * 번호 선택과 처음·이전·다음·마지막 이동을 두 줄로 나누는 공통 페이지 이동.
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
  const controls = [
    { text: '처음', label: '처음 페이지', target: 1, disabled: page <= 1 },
    {
      text: '이전',
      label: '이전 페이지',
      target: page - 1,
      disabled: page <= 1,
    },
    {
      text: '다음',
      label: '다음 페이지',
      target: page + 1,
      disabled: page >= totalPages,
    },
    {
      text: '마지막',
      label: '마지막 페이지',
      target: totalPages,
      disabled: page >= totalPages,
    },
  ];

  return (
    <nav
      className="preview-pagination"
      aria-label={label}
      aria-describedby={totalPages > 1 ? summaryId : undefined}
    >
      <ul className="preview-pagination-list">
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
      <ul className="preview-pagination-list preview-pagination-controls">
        {controls.map((control) => (
          <li key={control.label}>
            {control.disabled ? (
              <Button
                type="button"
                variant="outline"
                className="preview-page-jump"
                aria-label={control.label}
                disabled
              >
                {control.text}
              </Button>
            ) : (
              <Button asChild variant="outline" className="preview-page-jump">
                <Link
                  to={hrefForPage(control.target)}
                  aria-label={control.label}
                  onClick={onNavigate}
                >
                  {control.text}
                </Link>
              </Button>
            )}
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
