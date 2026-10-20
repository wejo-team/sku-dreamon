import { useEffect, useRef } from 'react';
import { useLocation, useSearchParams } from 'react-router';

export const REFERENCE_PAGE_SIZE = 6;

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
