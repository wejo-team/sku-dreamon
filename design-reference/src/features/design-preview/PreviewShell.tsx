import { useEffect, useRef } from 'react';
import {
  Layers2,
  Search,
  UserRound,
  ArrowLeft,
  MessageCircle,
} from 'lucide-react';
import { Link, Outlet, useLocation } from 'react-router';
import { previewPath } from './data';
import { Notifications } from './Notifications';

export function PreviewShell() {
  const location = useLocation();
  const shell = useRef<HTMLDivElement>(null);
  const main = useRef<HTMLElement>(null);
  const isAuth = /\/(login|signup)$/.test(location.pathname);
  const isAi = /\/ai\/?$/.test(location.pathname);
  const fromAi =
    new URLSearchParams(location.search).get('from') === previewPath('/ai');
  const teamId = location.pathname.match(/\/teams\/([^/]+)$/)?.[1];
  const teamView = teamId
    ? new URLSearchParams(location.search).get('view')
    : null;
  const isWorkspaceTeam =
    teamId === 'new' || teamView === 'space' || teamView === 'applicants';
  const active =
    isAi || fromAi
      ? 'ai'
      : isWorkspaceTeam || /\/(workspace|applicants)/.test(location.pathname)
        ? 'workspace'
        : /\/(profile|login|signup)/.test(location.pathname)
          ? 'profile'
          : 'explore';
  useEffect(() => {
    const previousTitle = document.title;
    document.title = '서경드림온';
    return () => {
      document.title = previousTitle;
    };
  }, []);
  useEffect(() => {
    window.scrollTo(0, 0);
    main.current?.focus({ preventScroll: true });
  }, [location.pathname, teamView]);
  useEffect(() => {
    const node = shell.current;
    const viewport = window.visualViewport;
    if (!isAi || !node || !viewport) return;
    // Keep the composer above mobile keyboards without overriding pinch zoom.
    const resize = () => {
      if (viewport.scale === 1) {
        node.style.setProperty(
          '--preview-ai-viewport-height',
          `${viewport.height}px`,
        );
      } else {
        node.style.removeProperty('--preview-ai-viewport-height');
      }
    };
    resize();
    viewport.addEventListener('resize', resize);
    return () => {
      viewport.removeEventListener('resize', resize);
      node.style.removeProperty('--preview-ai-viewport-height');
    };
  }, [isAi]);
  const nav = (
    <>
      {[
        { id: 'explore', title: '탐색', to: '/explore', icon: Search },
        { id: 'ai', title: 'AI', to: '/ai', icon: MessageCircle },
        {
          id: 'workspace',
          title: '워크스페이스',
          to: '/workspace',
          icon: Layers2,
        },
        { id: 'profile', title: '프로필', to: '/profile', icon: UserRound },
      ].map((item) => (
        <Link
          key={item.id}
          to={previewPath(item.to)}
          aria-current={active === item.id ? 'page' : undefined}
        >
          <item.icon size={21} strokeWidth={1.8} aria-hidden="true" />
          <span>{item.title}</span>
        </Link>
      ))}
    </>
  );
  return (
    <div
      ref={shell}
      className={`dreamon-preview${isAuth ? ' preview-auth-shell' : ''}${isAi ? ' preview-ai-shell' : ''}`}
    >
      <a className="preview-skip" href="#preview-main">
        본문으로 바로가기
      </a>
      <header className="preview-header">
        <div className="preview-header-inner">
          <Link
            className="preview-brand"
            to={previewPath('/explore')}
            aria-label="서경드림온 탐색"
          >
            <span className="preview-brand-mark">
              <img
                src="/brand/dreamon-logo.png"
                alt=""
                width={40}
                height={40}
              />
            </span>
            <img
              className="preview-wordmark"
              src="/brand/dreamon-wordmark.svg"
              alt=""
              width={140}
              height={33}
            />
          </Link>
          {!isAuth && (
            <nav className="preview-desktop-nav" aria-label="주 메뉴">
              {nav}
            </nav>
          )}
          {isAuth ? (
            <Link className="preview-auth-home" to={previewPath('/explore')}>
              <ArrowLeft size={16} aria-hidden="true" />
              탐색으로
            </Link>
          ) : (
            <Notifications />
          )}
        </div>
      </header>
      <main
        id="preview-main"
        ref={main}
        tabIndex={-1}
        className={`preview-main${isAuth ? ' preview-main-auth' : ''}`}
      >
        <Outlet />
      </main>
      {!isAuth && (
        <nav className="preview-mobile-nav" aria-label="주 메뉴">
          {nav}
        </nav>
      )}
    </div>
  );
}
