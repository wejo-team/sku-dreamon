import { useEffect } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { useNavigate } from 'react-router';
import { previewPath } from './data';

export function LoadingPage() {
  const navigate = useNavigate();
  useEffect(() => {
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (document.fonts?.ready ?? Promise.resolve()).then(() => {
        if (!cancelled) navigate(previewPath('/explore'), { replace: true });
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
          <ArrowUpRight size={48} strokeWidth={2.2} aria-hidden="true" />
        </span>
        <h1>서경드림온</h1>
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
