/**
 * [참조 출처]
 * 1. docs/design/tokens.md - 헤더 워드마크 SVG, 마스코트 로고, 4탭 모바일 하단 내비게이션 규격
 * 2. docs/design/screens.md - 공통 PreviewShell, visualViewport 키보드 대응, 상단 알림함 명세
 * 3. docs/design/assets/wordmark-explore-390.png - 헤더 및 탐색 레이아웃 스크린샷
 * 4. docs/development/frontend.md - 모바일 우선 유동 너비(320px~480px) 및 시맨틱 링크/버튼 보장
 * 5. design-reference/src/features/design-preview/PreviewShell.tsx - Shell 컴포넌트 원본
 *
 * [PR #120 리뷰 반영] 알림 상태·처리는 features/notifications/NotificationInbox로 분리하고,
 * 이 파일에는 헤더·본문·하단 메뉴 배치만 남겼습니다.
 */

import { useEffect, useRef, type ReactNode } from 'react';
import {
  ArrowLeft,
  Layers2,
  MessageCircle,
  Search,
  UserRound,
} from 'lucide-react';
import { Link, useLocation } from 'react-router';
import { NotificationInbox } from '@/features/notifications/NotificationInbox';

const navItems = [
  { id: 'explore', label: '탐색', to: '/explore', icon: Search },
  { id: 'ai', label: 'AI', to: '/ai', icon: MessageCircle },
  { id: 'workspace', label: '워크스페이스', to: '/workspace', icon: Layers2 },
  { id: 'profile', label: '프로필', to: '/profile', icon: UserRound },
];

// [출처 1, 2] 현재 경로에 따른 활성 탭 판별
function getActiveTab(pathname: string) {
  if (pathname.startsWith('/ai')) return 'ai';
  if (
    pathname.startsWith('/workspace') ||
    pathname.startsWith('/teams') ||
    pathname.startsWith('/applicants')
  )
    return 'workspace';
  if (
    pathname.startsWith('/profile') ||
    pathname.startsWith('/login') ||
    pathname.startsWith('/signup')
  )
    return 'profile';
  return 'explore';
}

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const isAuth = ['/login', '/signup'].includes(location.pathname);
  const isAi = location.pathname.startsWith('/ai');
  const shellRef = useRef<HTMLDivElement>(null);

  // [출처 2, 5] 모바일 소프트 키보드 대응을 위한 visualViewport 이벤트 리스너
  // TODO(AI 화면 연결): --ai-viewport-height를 소비하는 높이·스크롤 CSS를 AI 화면 구현 시 함께 추가합니다.
  useEffect(() => {
    const node = shellRef.current;
    const viewport = window.visualViewport;
    if (!isAi || !node || !viewport) return;

    const resize = () => {
      if (viewport.scale === 1) {
        node.style.setProperty('--ai-viewport-height', `${viewport.height}px`);
      } else {
        node.style.removeProperty('--ai-viewport-height');
      }
    };
    resize();
    viewport.addEventListener('resize', resize);
    return () => {
      viewport.removeEventListener('resize', resize);
      node?.style.removeProperty('--ai-viewport-height');
    };
  }, [isAi]);

  const activeTab = getActiveTab(location.pathname);

  return (
    <div ref={shellRef} className="dreamon-viewport shadow-lg">
      {/* [출처 1, 3] 모바일 상단 공통 헤더 */}
      <header className="sticky top-0 z-40 flex h-16 w-full items-center justify-between border-b border-border bg-card px-4 backdrop-blur-xs">
        <Link
          to="/explore"
          className="flex items-center gap-2.5 focus-visible:outline-2 focus-visible:outline-ring"
          aria-label="서경드림온 홈으로 이동"
        >
          <img
            src="/brand/dreamon-logo.png"
            alt=""
            width={36}
            height={36}
            className="size-9 object-contain"
          />
          <img
            src="/brand/dreamon-wordmark.svg"
            alt="서경드림온"
            width={130}
            height={30}
            className="h-7 w-auto object-contain"
          />
        </Link>

        {isAuth ? (
          <Link
            to="/explore"
            className="flex min-h-11 items-center gap-1 text-sm font-medium text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft size={16} aria-hidden="true" />
            탐색으로
          </Link>
        ) : (
          <NotificationInbox />
        )}
      </header>

      {/* [출처 4] 메인 콘텐츠 스크롤 영역. 하단 메뉴 전체 높이(safe-area 포함) + 32px 여백만큼 비워 가림을 막습니다. */}
      <main
        id="main-content"
        className={
          isAuth
            ? 'flex-1 pb-8'
            : 'flex-1 pb-[calc(var(--bottom-nav-height)+2rem)]'
        }
      >
        {children}
      </main>

      {/* [출처 1, 3] 하단 고정 4개 내비게이션 탭 바
          [PR #120 리뷰 반영] 높이 = 64px + safe-area, 탭은 고정 48px 폭 대신 공간을 1/4씩 나눠
          '워크스페이스'가 줄바꿈되거나 아이콘이 줄어들지 않게 합니다. */}
      {!isAuth && (
        <nav
          aria-label="하단 주 메뉴"
          className="fixed bottom-0 z-40 flex h-(--bottom-nav-height) w-full max-w-[480px] items-start border-t border-border bg-card/95 px-2 pt-2 pb-[env(safe-area-inset-bottom)] backdrop-blur-sm"
        >
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <Link
                key={item.id}
                to={item.to}
                aria-current={isActive ? 'page' : undefined}
                className={`flex h-12 min-w-0 flex-1 flex-col items-center justify-center gap-0.5 rounded-control text-xs transition-colors focus-visible:outline-2 focus-visible:outline-ring ${
                  isActive
                    ? 'font-bold text-primary'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <item.icon
                  size={22}
                  strokeWidth={isActive ? 2.2 : 1.8}
                  aria-hidden="true"
                  className="shrink-0"
                />
                <span className="whitespace-nowrap">{item.label}</span>
              </Link>
            );
          })}
        </nav>
      )}
    </div>
  );
}
