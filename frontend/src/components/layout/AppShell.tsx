/**
 * [참조 출처]
 * 1. docs/design/tokens.md - 헤더 워드마크 SVG, 마스코트 로고, 4탭 모바일 하단 내비게이션 규격
 * 2. docs/design/screens.md - 공통 PreviewShell, visualViewport 키보드 대응, 상단 알림함 명세
 * 3. docs/design/assets/wordmark-explore-390.png - 헤더 및 탐색 레이아웃 스크린샷
 * 4. docs/development/frontend.md - 모바일 우선 유동 너비(320px~480px) 및 시맨틱 링크/버튼 보장
 * 5. design-reference/src/features/design-preview/PreviewShell.tsx - Shell 컴포넌트 원본
 */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  Bell,
  CheckCheck,
  ChevronRight,
  Layers2,
  MessageCircle,
  Search,
  UserRound,
  ArrowLeft,
} from 'lucide-react';
import { Link, useLocation } from 'react-router';
import { Button } from '@/components/ui/button';
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer';
import {
  initialNotifications,
  type NotificationItem,
} from '@/features/data/mock-data';

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const isAuth = ['/login', '/signup'].includes(location.pathname);
  const isAi = location.pathname.startsWith('/ai');
  const [notifications, setNotifications] =
    useState<NotificationItem[]>(initialNotifications);
  const [notifOpen, setNotifOpen] = useState(false);
  const shellRef = useRef<HTMLDivElement>(null);

  // [출처 2, 5] 모바일 소프트 키보드 대응을 위한 visualViewport 이벤트 리스너
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

  // [출처 1, 2] 현재 경로에 따른 활성 탭 판별
  const getActiveTab = () => {
    if (location.pathname.startsWith('/ai')) return 'ai';
    if (
      location.pathname.startsWith('/workspace') ||
      location.pathname.startsWith('/teams') ||
      location.pathname.startsWith('/applicants')
    )
      return 'workspace';
    if (
      location.pathname.startsWith('/profile') ||
      location.pathname.startsWith('/login') ||
      location.pathname.startsWith('/signup')
    )
      return 'profile';
    return 'explore';
  };

  const activeTab = getActiveTab();
  const unreadCount = notifications.filter((n) => !n.read).length;

  const markAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  };

  const navItems = [
    { id: 'explore', label: '탐색', to: '/explore', icon: Search },
    { id: 'ai', label: 'AI', to: '/ai', icon: MessageCircle },
    { id: 'workspace', label: '워크스페이스', to: '/workspace', icon: Layers2 },
    { id: 'profile', label: '프로필', to: '/profile', icon: UserRound },
  ];

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
          <div className="relative">
            {/* [출처 2] 상단 우측 알림 버튼 (최소 44px 터치 타깃 보장) */}
            <Button
              variant="outline"
              onClick={() => setNotifOpen(true)}
              aria-label={`알림 ${unreadCount}건`}
              className="relative size-11 rounded-full border-border bg-card p-0 hover:bg-muted"
            >
              <Bell size={19} className="text-foreground" aria-hidden="true" />
              {unreadCount > 0 && (
                <span className="absolute -top-1 -right-1 flex size-5 items-center justify-center rounded-full bg-destructive text-[11px] font-bold text-white shadow-xs">
                  {unreadCount}
                </span>
              )}
            </Button>
          </div>
        )}
      </header>

      {/* [출처 4] 메인 콘텐츠 스크롤 영역 */}
      <main id="main-content" className="flex-1 pb-24">
        {children}
      </main>

      {/* [출처 1, 3] 하단 고정 4개 내비게이션 탭 바 */}
      {!isAuth && (
        <nav
          aria-label="하단 주 메뉴"
          className="fixed bottom-0 z-40 flex h-16 w-full max-w-[480px] items-center justify-around border-t border-border bg-card/95 px-2 backdrop-blur-sm"
        >
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <Link
                key={item.id}
                to={item.to}
                aria-current={isActive ? 'page' : undefined}
                className={`flex size-12 min-w-11 flex-col items-center justify-center gap-0.5 rounded-lg text-xs transition-colors focus-visible:outline-2 focus-visible:outline-ring ${
                  isActive
                    ? 'font-bold text-primary'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                <item.icon
                  size={22}
                  strokeWidth={isActive ? 2.2 : 1.8}
                  aria-hidden="true"
                />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>
      )}

      {/* [출처 2] 알림 드로어 (Notification Inbox) */}
      <Drawer open={notifOpen} onOpenChange={setNotifOpen}>
        <DrawerContent className="p-4">
          <DrawerHeader className="flex flex-row items-center justify-between pb-2">
            <div>
              <DrawerTitle className="text-base font-bold">알림함</DrawerTitle>
              <DrawerDescription className="text-xs">
                업무 및 지원 상태 변경 알림
              </DrawerDescription>
            </div>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={markAllRead}
                className="flex h-9 items-center gap-1 text-xs font-medium text-primary hover:text-primary/80"
              >
                <CheckCheck size={15} /> 모두 읽음
              </button>
            )}
          </DrawerHeader>

          <div className="mt-2 flex flex-col gap-2.5">
            {notifications.length === 0 ? (
              <p className="py-8 text-center text-sm text-muted-foreground">
                도착한 알림이 없어요.
              </p>
            ) : (
              notifications.map((item) => (
                <Link
                  key={item.id}
                  to={item.to}
                  onClick={() => {
                    setNotifications((prev) =>
                      prev.map((n) =>
                        n.id === item.id ? { ...n, read: true } : n,
                      ),
                    );
                    setNotifOpen(false);
                  }}
                  className={`flex items-start gap-3 rounded-xl border p-3.5 transition-colors ${
                    item.read
                      ? 'border-border bg-card'
                      : 'border-accent bg-accent/40 font-medium'
                  }`}
                >
                  <div className="flex-1">
                    <p className="text-sm font-semibold text-foreground">
                      {item.title}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {item.description}
                    </p>
                    {item.occurredAt && (
                      <span className="mt-2 block text-[11px] text-muted-foreground/80">
                        {item.occurredAt}
                      </span>
                    )}
                  </div>
                  <ChevronRight
                    size={16}
                    className="text-muted-foreground shrink-0 mt-1"
                  />
                </Link>
              ))
            )}
          </div>
        </DrawerContent>
      </Drawer>
    </div>
  );
}
