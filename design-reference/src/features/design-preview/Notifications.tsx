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
import { previewPath, type ApplicationStatus } from './data';
import { isNotificationRecipient } from './notification-state';
import { usePreview } from './preview-context';

type Notification = {
  id: string;
  title: string;
  description: string;
  to: string;
  kind: 'applicant' | 'application';
  read: boolean;
};

const icons = {
  applicant: UserRoundPlus,
  application: ClipboardCheck,
};
const applicationTitles: Record<ApplicationStatus, string> = {
  지원취소: '지원이 취소됐어요',
  지원완료: '지원이 접수됐어요',
  검토중: '팀에서 지원서를 검토하고 있어요',
  선발: '지원한 팀에서 선발됐어요',
  미선발: '이번 모집에서는 선발되지 않았어요',
};

export function Notifications() {
  const { signedIn } = usePreview();
  return <NotificationInbox key={signedIn ? 'member' : 'guest'} />;
}

function NotificationInbox() {
  const {
    signedIn,
    teams,
    notifications: history,
    markNotificationsRead,
  } = usePreview();
  const location = useLocation();
  const navigate = useNavigate();
  const failedOnce = useRef(false);
  const [failedRead, setFailedRead] = useState<{
    ids: string[];
    to?: string;
  } | null>(null);
  const open = location.state?.notificationInbox === true;
  const setOpen = (next: boolean) => {
    if (next === open) return;
    if (next) {
      navigate(`${location.pathname}${location.search}`, {
        state: { ...location.state, notificationInbox: true },
      });
    } else {
      navigate(-1);
    }
  };
  const [filter, setFilter] = useState<'all' | 'unread'>('all');
  const notifications: Notification[] = signedIn
    ? history
        .filter((item) => isNotificationRecipient(item, teams))
        .reverse()
        .map((item) => ({
          id: item.id,
          kind: item.kind,
          title:
            item.kind === 'application'
              ? applicationTitles[item.status]
              : `${item.applicantName} 님이 지원했어요`,
          description: `${item.teamName} · ${item.role} 지원`,
          to:
            item.kind === 'application'
              ? previewPath('/workspace?view=applications')
              : previewPath(`/applicants/${item.applicationId}`),
          read: item.read,
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
                to={`${previewPath('/login')}?returnTo=${encodeURIComponent(returnTo)}`}
                onClick={(event) => {
                  event.preventDefault();
                  navigate(
                    `${previewPath('/login')}?returnTo=${encodeURIComponent(returnTo)}`,
                    { replace: true },
                  );
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
