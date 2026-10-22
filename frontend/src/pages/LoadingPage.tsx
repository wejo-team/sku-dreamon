/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/LoadingPage.tsx - 시작 안내 원본
 * 2. docs/design/screens.md - 「시작·없는 경로」 시작 안내 후 탐색으로 이동
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router';

// [출처 1, 2] 로고·워드마크 표시 후 탐색으로 이동
export function LoadingPage() {
  const navigate = useNavigate();
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (document.fonts?.ready ?? Promise.resolve()).then(() => {
        if (!cancelled) navigate('/explore', { replace: true });
      });
    }, 650);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [navigate]);
  return (
    <main
      className="dreamon-preview service-loading"
      aria-label="서경드림온 시작"
    >
      <div className="service-loading-brand">
        <span className="service-loading-mark">
          <img src="/brand/dreamon-logo.png" alt="" width={96} height={96} />
        </span>
        <h1>
          <img
            className="service-loading-wordmark"
            src="/brand/dreamon-wordmark.svg"
            alt="서경드림온"
            width={240}
            height={56}
          />
        </h1>
      </div>
      <div
        role="status"
        aria-label="불러오는 중"
        className="service-loading-status"
      >
        <span />
        <span />
        <span />
      </div>
    </main>
  );
}
