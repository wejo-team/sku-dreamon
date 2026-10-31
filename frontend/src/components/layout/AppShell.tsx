/**
 * [참조 출처]
 * 1. docs/design/screens.md - 제품 공통 상단·하단 탐색과 경로
 * 2. docs/design/tokens.md - 「모바일 상호작용 확인」 하단 4탭, 탐색 검색 옆 알림, 루트 화면 h1.sr-only
 * 3. docs/design/screens.md - 화면별 경로와 활성 탭, AI 화면 visualViewport 대응
 * 4. docs/design/assets/explore-layout-20261101-390.png - 검색 중심 탐색과 압축 하단 메뉴
 * 5. docs/development/frontend.md - 「모바일 UI」 safe-area, 키보드, 시맨틱 링크
 *
 * 하단 메뉴의 safe-area 높이·탭 등분과 AI 화면의 --preview-ai-viewport-height 소비는
 * styles/design-preview.css·service-ui.css·explore-layout.css가 담당합니다.
 */

import { useEffect, useRef } from 'react';
import {
  ArrowLeft,
  Layers2,
  MessageCircle,
  Search,
  UserRound,
} from 'lucide-react';
import { Link, Outlet, useLocation } from 'react-router';

// [출처 2] 팀 메뉴는 기존 워크스페이스 경로를 유지합니다.
const navItems = [
  { id: 'explore', title: '탐색', to: '/explore', icon: Search },
  { id: 'ai', title: 'AI', to: '/ai', icon: MessageCircle },
  { id: 'workspace', title: '팀', to: '/workspace', icon: Layers2 },
  { id: 'profile', title: '프로필', to: '/profile', icon: UserRound },
];

export function AppShell() {
  const location = useLocation();
  const shell = useRef<HTMLDivElement>(null);
  const main = useRef<HTMLElement>(null);
  const isAuth = /\/(login|signup)$/.test(location.pathname);
  const isAi = /^\/ai\/?$/.test(location.pathname);
  const isExplore = /^\/explore\/?$/.test(location.pathname);
  const params = new URLSearchParams(location.search);
  const fromAi = params.get('from') === '/ai';
  const teamId = location.pathname.match(/\/teams\/([^/]+)$/)?.[1];
  const teamView = teamId ? params.get('view') : null;
  const isWorkspaceTeam =
    teamId === 'new' || teamView === 'space' || teamView === 'applicants';
  // [출처 1, 3] 팀 공간·지원자 관리·팀 만들기는 워크스페이스, AI에서 연 상세는 AI 탭으로 표시합니다.
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

  // [출처 5] 화면 전환 시 맨 위로 이동하고 본문으로 포커스를 옮겨 스크린리더가 새 화면을 읽게 합니다.
  useEffect(() => {
    window.scrollTo(0, 0);
    main.current?.focus({ preventScroll: true });
  }, [location.pathname, teamView]);

  // [출처 3, 5] 모바일 키보드가 열려도 AI 입력창이 가려지지 않도록 visualViewport 높이를 전달합니다.
  // 확대(scale ≠ 1) 중에는 사용자의 확대를 덮어쓰지 않습니다.
  useEffect(() => {
    const node = shell.current;
    const viewport = window.visualViewport;
    if (!isAi || !node || !viewport) return;
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

  const nav = navItems.map((item) => (
    <Link
      key={item.id}
      to={item.to}
      aria-current={active === item.id ? 'page' : undefined}
    >
      <item.icon size={21} strokeWidth={1.8} aria-hidden="true" />
      <span>{item.title}</span>
    </Link>
  ));

  return (
    <div
      ref={shell}
      className={`dreamon-preview${isAuth ? ' preview-auth-shell' : ''}${isAi ? ' preview-ai-shell' : ''}${isExplore ? ' preview-explore-shell' : ''}`}
    >
      <a className="preview-skip" href="#preview-main">
        본문으로 바로가기
      </a>
      <main
        id="preview-main"
        ref={main}
        tabIndex={-1}
        className={`preview-main${isAuth ? ' preview-main-auth' : ''}`}
      >
        {isAuth && (
          <Link className="preview-auth-home" to="/explore">
            <ArrowLeft size={16} aria-hidden="true" />
            탐색으로
          </Link>
        )}
        <Outlet />
      </main>
      {/* [출처 2, 5] 하단 4탭. 높이에 safe-area를 포함하고 탭은 폭을 등분합니다(styles/service-ui.css). */}
      {!isAuth && (
        <nav className="preview-mobile-nav" aria-label="주 메뉴">
          {nav}
        </nav>
      )}
    </div>
  );
}
