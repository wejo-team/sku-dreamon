/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/use-list-page.ts - 목록 페이지 계산 원본
 * 2. docs/design/screens.md - 「확인할 상태와 연결」 페이지당 6개, 조건 변경 시 1페이지, 잘못된 페이지 보정
 * 3. docs/development/frontend.md - 「화면과 상태」 공유 가능한 검색·필터·페이지 값은 URL 우선
 */

import { useEffect, useRef } from 'react';
import { useLocation, useSearchParams } from 'react-router';

// [출처 2] 페이지당 6개(운영 페이지 크기는 미정)
export const REFERENCE_PAGE_SIZE = 6;

// [출처 2, 3] URL의 page를 읽고 범위를 보정
export function useListPage(total: number, parameter = 'page') {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const raw = params.get(parameter);
  const requested = raw && /^[1-9]\d*$/.test(raw) ? Number(raw) : 1;
  const totalPages = Math.ceil(total / REFERENCE_PAGE_SIZE);
  const page = Math.min(
    Number.isSafeInteger(requested) ? requested : 1,
    Math.max(1, totalPages),
  );
  const conditions = new URLSearchParams(params);
  conditions.delete(parameter);
  const scope = location.pathname + '?' + conditions.toString();
  const previous = useRef({ page, scope });

  useEffect(() => {
    const canonical = page === 1 ? null : String(page);
    if (raw !== canonical) {
      const next = new URLSearchParams(params);
      if (canonical) next.set(parameter, canonical);
      else next.delete(parameter);
      setParams(next, { replace: true });
    }
  }, [page, parameter, params, raw, setParams]);

  useEffect(() => {
    if (previous.current.page !== page && previous.current.scope === scope) {
      headingRef.current?.focus({ preventScroll: true });
      headingRef.current?.scrollIntoView?.({ block: 'start' });
    }
    previous.current = { page, scope };
  }, [page, scope]);

  const hrefForPage = (target: number) => {
    const next = new URLSearchParams(params);
    if (target === 1) next.delete(parameter);
    else next.set(parameter, String(target));
    const search = next.toString();
    return location.pathname + (search ? `?${search}` : '');
  };

  return {
    page,
    totalPages,
    start: (page - 1) * REFERENCE_PAGE_SIZE,
    end: page * REFERENCE_PAGE_SIZE,
    hrefForPage,
    headingRef,
  };
}
