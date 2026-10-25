/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/Notifications.tsx - 상단 알림함 원본
 * 2. docs/specs/notifications.md - 읽음·모두 읽음·관련 화면 이동, 실패 시 읽음·개수 유지 후 재시도
 * 3. docs/design/screens.md - 「확인할 상태와 연결」 열기만으로 읽음 처리하지 않음, 뒤로 가기·닫기는 알림함만 닫기
 * 4. docs/design/tokens.md - 상단 우측 알림과 하단 프로필의 역할 구분
 */

import { useRef, useState } from 'react';
import {
  Bell,
  CheckCheck,
  ChevronRight,
  ClipboardCheck,
  RotateCcw,
  UserRoundPlus,
  X,
} from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router';
import { Alert, AlertDescription } from '@/components/ui/alert';
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
import type { Notification } from '@/features/notifications/api';
import { useDemo } from '@/features/demo/demo-context';

// 화면 표시용 항목. 제목·본문은 API의 Notification.title·body를 그대로 사용합니다.
type InboxItem = {
  id: string;
  title: string;
  description: string;
  to: string;
  kind: Notification['kind'];
  read: boolean;
};

const icons = {
  new_application: UserRoundPlus,
  application_status_changed: ClipboardCheck,
};

// [출처 2, 3, 4] 로그인 여부별 알림함, history로 열림 상태 관리
export function Notifications() {
  const { signedIn } = useDemo();
  return <NotificationInbox key={signedIn ? 'member' : 'guest'} />;
}

function NotificationInbox() {
  const { signedIn, notifications: history, markNotificationsRead } = useDemo();
  const location = useLocation();
  const navigate = useNavigate();
  const failedOnce = useRef(false);
  const [failedRead, setFailedRead] = useState<{
    ids: string[];
    to?: string;
  } | null>(null);
  const open = location.state?.notificationInbox === true;
  // [출처 3] 열기는 같은 경로에 알림함 history를 추가하고, 닫기·뒤로 가기는 그 항목만 되돌립니다.
  // 새로고침으로 첫 history 항목에서 열린 경우에는 페이지를 벗어나지 않도록 표시만 지웁니다.
  const setOpen = (next: boolean) => {
    if (next === open) return;
    const path = `${location.pathname}${location.search}`;
    if (next) {
      navigate(path, {
        state: { ...location.state, notificationInbox: true },
      });
    } else if ((window.history.state?.idx ?? 1) > 0) {
      navigate(-1);
    } else {
      navigate(path, {
        replace: true,
        state: { ...location.state, notificationInbox: undefined },
      });
    }
  };
  const [filter, setFilter] = useState<'all' | 'unread'>('all');
  // [출처 2] 본인 알림만(상태에서 수신자 관계를 이미 확인), 정렬 occurredAt DESC, id DESC
  const notifications: InboxItem[] = signedIn
    ? [...history]
        .sort(
          (left, right) =>
            right.occurredAt.localeCompare(left.occurredAt) ||
            right.id.localeCompare(left.id),
        )
        .map((item) => ({
          id: item.id,
          kind: item.kind,
          title: item.title,
          description: item.body,
          to:
            item.kind === 'application_status_changed'
              ? '/workspace?view=applications'
              : `/applicants/${item.applicationId}`,
          read: item.readAt !== null,
        }))
    : [];

  const unread = notifications.filter((item) => !item.read);
  const visible = filter === 'unread' ? unread : notifications;
  const markRead = (ids: string[], to?: string) => {
    // A single failed write makes the recovery state reproducible in this reference.
    if (
      ids.some((id) => unread.some((item) => item.id === id)) &&
      new URLSearchParams(location.search).get('scenario') ===
        'notification-error' &&
      !failedOnce.current
    ) {
      failedOnce.current = true;
      setFailedRead({ ids, to });
      return false;
    }
    markNotificationsRead(ids);
    setFailedRead(null);
    return true;
  };
  const retryRead = () => {
    if (!failedRead || !markRead(failedRead.ids, failedRead.to)) return;
    if (failedRead.to) {
      navigate(failedRead.to, { replace: true });
    }
  };
  const returnTo = `${location.pathname}${location.search}`;

  return (
    <Drawer open={open} onOpenChange={setOpen}>
      <DrawerTrigger asChild>
        <Button
          variant="ghost"
          className="preview-notification-trigger"
          aria-label={
            unread.length ? `알림, 읽지 않은 알림 ${unread.length}개` : '알림'
          }
        >
          <Bell size={21} strokeWidth={1.8} aria-hidden="true" />
          {!!unread.length && (
            <span className="preview-notification-dot" aria-hidden="true" />
          )}
        </Button>
      </DrawerTrigger>
      <DrawerContent className="dreamon-preview preview-drawer preview-notifications">
        <DrawerHeader>
          <div className="preview-notifications-heading">
            <DrawerTitle>알림</DrawerTitle>
            <DrawerClose asChild>
              <Button
                variant="ghost"
                className="preview-notifications-close"
                aria-label="알림 닫기"
              >
                <X size={20} aria-hidden="true" />
              </Button>
            </DrawerClose>
          </div>
          <DrawerDescription className="sr-only">
            지원 현황과 팀 소식을 확인하세요. 알림을 누르면 관련 화면으로
            이동합니다.
          </DrawerDescription>
        </DrawerHeader>
        {signedIn ? (
          <>
            <div className="preview-notifications-tools">
              <div
                className="preview-notifications-filters"
                role="group"
                aria-label="알림 필터"
              >
                <Button
                  variant="ghost"
                  aria-pressed={filter === 'all'}
                  onClick={() => setFilter('all')}
                >
                  전체
                </Button>
                <Button
                  variant="ghost"
                  aria-pressed={filter === 'unread'}
                  onClick={() => setFilter('unread')}
                >
                  읽지 않음 <span>{unread.length}</span>
                </Button>
              </div>
              <Button
                variant="ghost"
                className="preview-notifications-read-all"
                disabled={!unread.length}
                onClick={() => markRead(unread.map((item) => item.id))}
              >
                <CheckCheck size={16} aria-hidden="true" />
                모두 읽음
              </Button>
            </div>
            {failedRead && (
              <Alert role="alert" className="mx-5 mb-3 w-auto">
                <AlertDescription>
                  <p>읽음 상태를 저장하지 못했어요. 다시 시도해 주세요.</p>
                  <Button
                    type="button"
                    variant="outline"
                    className="mt-2 justify-self-start"
                    onClick={retryRead}
                  >
                    <RotateCcw size={16} aria-hidden="true" />
                    다시 시도
                  </Button>
                </AlertDescription>
              </Alert>
            )}
            <p className="sr-only" role="status">
              읽지 않은 알림 {unread.length}개
            </p>
            <div className="preview-notifications-body">
              {visible.length ? (
                <ul
                  className="preview-notifications-list"
                  aria-label="알림 목록"
                >
                  {visible.map((item) => {
                    const Icon = icons[item.kind];
                    const isUnread = !item.read;
                    return (
                      <li key={item.id}>
                        <Link
                          to={item.to}
                          className="preview-notification-item"
                          data-unread={isUnread || undefined}
                          onClick={(event) => {
                            event.preventDefault();
                            if (!markRead([item.id], item.to)) return;
                            navigate(item.to, { replace: true });
                          }}
                        >
                          <span className="preview-notification-icon">
                            <Icon
                              size={20}
                              strokeWidth={1.8}
                              aria-hidden="true"
                            />
                          </span>
                          <span className="preview-notification-copy">
                            <strong>{item.title}</strong>
                            <span>{item.description}</span>
                          </span>
                          <span className="preview-notification-trailing">
                            {isUnread && (
                              <span className="preview-notification-unread">
                                <span className="sr-only">읽지 않음</span>
                              </span>
                            )}
                            <ChevronRight size={16} aria-hidden="true" />
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <div className="preview-notifications-empty">
                  {filter === 'unread' && notifications.length ? (
                    <CheckCheck
                      size={28}
                      strokeWidth={1.5}
                      aria-hidden="true"
                    />
                  ) : (
                    <Bell size={28} strokeWidth={1.5} aria-hidden="true" />
                  )}
                  <h3>
                    {filter === 'unread' && notifications.length
                      ? '모든 알림을 확인했어요'
                      : '아직 알림이 없어요'}
                  </h3>
                  <p>새로운 지원 현황과 팀 소식이 오면 알려드릴게요.</p>
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="preview-notifications-empty">
            <Bell size={28} strokeWidth={1.5} aria-hidden="true" />
            <h3>로그인하고 알림을 확인하세요</h3>
            <p>지원 현황과 팀 소식을 한곳에서 확인할 수 있어요.</p>
            <Button asChild>
              <Link
                to={`/login?returnTo=${encodeURIComponent(returnTo)}`}
                onClick={(event) => {
                  event.preventDefault();
                  navigate(`/login?returnTo=${encodeURIComponent(returnTo)}`, {
                    replace: true,
                  });
                }}
              >
                로그인
              </Link>
            </Button>
          </div>
        )}
      </DrawerContent>
    </Drawer>
  );
}
