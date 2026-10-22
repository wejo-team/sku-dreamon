/**
 * [참조 출처]
 * 1. docs/design/screens.md - 상단 알림함: 열기만으로 읽음 처리하지 않음, 뒤로 가기·닫기는 알림함만 닫기
 * 2. docs/specs/notifications.md - 알림 읽음·모두 읽음·관련 화면 이동 완료 조건
 * 3. design-reference/src/features/design-preview/Notifications.tsx - history 기반 열림 상태 원본
 * 4. docs/design/verification.md - 텍스트 명도 대비 기준
 *
 * [PR #120 리뷰 반영]
 * - AppShell이 화면 배치와 알림 상태·처리를 함께 맡던 구조를 이 컴포넌트 한 단위로 분리했습니다.
 * - 열림 상태를 컴포넌트 state가 아닌 history 항목(location.state)에 두어, 브라우저 뒤로 가기가
 *   경로를 바꾸지 않고 알림함만 닫도록 했습니다(출처 1, 3).
 */

import { useState } from 'react';
import { Bell, CheckCheck, ChevronRight, X } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router';
import { Button } from '@/components/ui/button';
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from '@/components/ui/drawer';
import {
  initialNotifications,
  type NotificationItem,
} from './mock-notifications';

export function NotificationInbox() {
  const location = useLocation();
  const navigate = useNavigate();
  const [notifications, setNotifications] =
    useState<NotificationItem[]>(initialNotifications);

  // [출처 1, 3] 열기는 같은 경로에 알림함 표시 history를 추가하고, 닫기는 그 항목을 되돌립니다.
  // 새로고침으로 첫 history 항목에서 열린 경우에는 뒤로 가지 않고 표시만 제거해 페이지를 벗어나지 않습니다.
  const open = location.state?.notificationInbox === true;
  const setOpen = (next: boolean) => {
    if (next === open) return;
    const path = `${location.pathname}${location.search}`;
    if (next) {
      navigate(path, { state: { ...location.state, notificationInbox: true } });
    } else if ((window.history.state?.idx ?? 1) > 0) {
      navigate(-1);
    } else {
      navigate(path, {
        replace: true,
        state: { ...location.state, notificationInbox: undefined },
      });
    }
  };

  const unreadCount = notifications.filter((n) => !n.read).length;

  const markRead = (ids?: string[]) => {
    setNotifications((prev) =>
      prev.map((n) => (!ids || ids.includes(n.id) ? { ...n, read: true } : n)),
    );
  };

  return (
    <Drawer open={open} onOpenChange={setOpen}>
      {/* [출처 1] 상단 우측 알림 버튼 (최소 44px 터치 타깃). 닫히면 포커스가 이 버튼으로 돌아옵니다. */}
      <DrawerTrigger asChild>
        <Button
          variant="outline"
          aria-label={
            unreadCount ? `알림, 읽지 않은 알림 ${unreadCount}개` : '알림'
          }
          className="relative size-11 rounded-full border-border bg-card p-0 hover:bg-muted"
        >
          <Bell size={19} className="text-foreground" aria-hidden="true" />
          {unreadCount > 0 && (
            <span
              aria-hidden="true"
              className="absolute -top-1 -right-1 flex size-5 items-center justify-center rounded-full bg-destructive text-[11px] font-bold text-white shadow-xs"
            >
              {unreadCount}
            </span>
          )}
        </Button>
      </DrawerTrigger>

      <DrawerContent className="p-4">
        <DrawerHeader className="pb-2">
          <div className="flex items-start justify-between gap-2">
            <div>
              <DrawerTitle className="text-base font-bold">알림함</DrawerTitle>
              <DrawerDescription className="text-xs">
                업무 및 지원 상태 변경 알림
              </DrawerDescription>
            </div>
            <DrawerClose asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label="알림 닫기"
                className="-mt-2 -mr-2"
              >
                <X aria-hidden="true" />
              </Button>
            </DrawerClose>
          </div>
          {unreadCount > 0 && (
            <button
              type="button"
              onClick={() => markRead()}
              className="flex min-h-11 items-center gap-1 self-end text-xs font-medium text-primary hover:text-primary-hover"
            >
              <CheckCheck size={15} aria-hidden="true" /> 모두 읽음
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
                onClick={(event) => {
                  // [출처 2, 3] 알림함 history 항목을 관련 화면으로 대체해 뒤로 가기 시 알림함이 다시 열리지 않게 합니다.
                  event.preventDefault();
                  markRead([item.id]);
                  navigate(item.to, { replace: true });
                }}
                className={`flex items-start gap-3 rounded-panel border p-3.5 transition-colors ${
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
                  {/* [출처 4] 작은 날짜도 보조색 토큰을 불투명하게 사용해 대비를 유지하고, 중요도는 크기·배치로 구분합니다. */}
                  {item.occurredAt && (
                    <span className="mt-2 block text-[11px] text-muted-foreground">
                      {item.occurredAt}
                    </span>
                  )}
                </div>
                {!item.read && <span className="sr-only">읽지 않음</span>}
                <ChevronRight
                  size={16}
                  aria-hidden="true"
                  className="mt-1 shrink-0 text-muted-foreground"
                />
              </Link>
            ))
          )}
        </div>
      </DrawerContent>
    </Drawer>
  );
}
