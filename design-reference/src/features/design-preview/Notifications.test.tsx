import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Link, MemoryRouter, useLocation, useNavigate } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { useState, type ReactNode } from 'react';
import { Notifications } from './Notifications';
import {
  initialApplicants,
  initialApplications,
  initialProfile,
  initialTeams,
} from './data';
import {
  PreviewContext,
  type PreviewState,
  usePreview,
} from './preview-context';
import { PreviewProvider } from './PreviewProvider';
import { initialNotifications } from './notification-state';

function Navigation() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <p>
        현재 경로: {location.pathname}
        {location.search}
      </p>
      <button onClick={() => navigate(-1)}>브라우저 뒤로</button>
      <Link to="/design-preview/profile">프로필로</Link>
    </>
  );
}

function RoutedInbox() {
  const location = useLocation();
  return <Notifications key={location.pathname} />;
}

function InboxState({
  initial,
  children,
}: {
  initial: PreviewState;
  children: ReactNode;
}) {
  const [notifications, setNotifications] = useState(initial.notifications);
  return (
    <PreviewContext
      value={{
        ...initial,
        notifications,
        markNotificationsRead: (ids) =>
          setNotifications((items) =>
            items.map((item) =>
              ids.includes(item.id) ? { ...item, read: true } : item,
            ),
          ),
      }}
    >
      {children}
    </PreviewContext>
  );
}

function ActivityControls() {
  const {
    signIn,
    saveProfile,
    profile,
    apply,
    applications,
    cancelApplication,
  } = usePreview();
  return (
    <>
      <button
        onClick={() => {
          signIn();
          saveProfile({ ...profile, visibility: { discoverable: true } });
        }}
      >
        지원 준비
      </button>
      <button onClick={() => apply('makers', '기획', '')}>
        공개 팀에 지원
      </button>
      <button onClick={() => apply('greenwave', '개발', '')}>
        내 팀에 지원 시도
      </button>
      <button
        onClick={() => {
          const latest = applications
            .filter(
              (item) => item.teamId === 'makers' && item.status !== '지원취소',
            )
            .at(-1);
          if (latest) cancelApplication(latest.id);
        }}
      >
        방금 지원 취소
      </button>
    </>
  );
}

function renderInbox(
  path = '/design-preview/explore',
  overrides: Partial<PreviewState> = {},
) {
  const state: PreviewState = {
    signedIn: true,
    profile: initialProfile,
    teams: initialTeams,
    applications: initialApplications,
    applicants: initialApplicants,
    notifications: initialNotifications({
      teams: initialTeams,
      applications: initialApplications,
      applicants: initialApplicants,
    }),
    markNotificationsRead: vi.fn(),
    signIn: vi.fn(),
    signOut: vi.fn(),
    saveProfile: vi.fn(),
    apply: vi.fn(() => true),
    selectApplicant: vi.fn(() => true),
    cancelApplication: vi.fn(() => true),
    closeRecruitment: vi.fn(() => true),
    reopenRecruitment: vi.fn(() => true),
    createTeam: vi.fn(() => 'new-team'),
    reset: vi.fn(),
    emptyWorkspace: vi.fn(),
    ...overrides,
  };
  render(
    <MemoryRouter initialEntries={[path]}>
      <InboxState initial={state}>
        <RoutedInbox />
        <Navigation />
      </InboxState>
    </MemoryRouter>,
  );
  return userEvent.setup();
}

async function openInbox(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /^알림(?:,|$)/ }));
  return screen.findByRole('dialog', { name: '알림' });
}

describe('official reference notifications', () => {
  it('shows no account notification or unread count to guests and preserves the login destination', async () => {
    const user = renderInbox('/design-preview/explore?tab=teams', {
      signedIn: false,
    });
    expect(screen.getByRole('button', { name: '알림' })).toBeInTheDocument();
    const drawer = await openInbox(user);
    expect(
      within(drawer).getByRole('heading', {
        name: '로그인하고 알림을 확인하세요',
      }),
    ).toBeInTheDocument();
    expect(
      within(drawer).queryByRole('list', { name: '알림 목록' }),
    ).not.toBeInTheDocument();
    expect(within(drawer).queryByText(/김서연/)).not.toBeInTheDocument();
    expect(
      within(drawer).queryByRole('button', { name: '모두 읽음' }),
    ).not.toBeInTheDocument();
    expect(
      within(drawer).getByRole('link', { name: '로그인' }),
    ).toHaveAttribute(
      'href',
      '/design-preview/login?returnTo=%2Fdesign-preview%2Fexplore%3Ftab%3Dteams',
    );
  });

  it('marks all read without deleting notifications and keeps that state across normal routes', async () => {
    const user = renderInbox();
    const drawer = await openInbox(user);
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 3개',
    );
    expect(within(drawer).getAllByRole('listitem')).toHaveLength(3);
    await user.click(within(drawer).getByRole('button', { name: '모두 읽음' }));
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 0개',
    );
    expect(within(drawer).getAllByRole('listitem')).toHaveLength(3);
    await user.click(
      within(drawer).getByRole('button', { name: /읽지 않음 0/ }),
    );
    expect(
      within(drawer).getByRole('heading', { name: '모든 알림을 확인했어요' }),
    ).toBeInTheDocument();
    await user.click(within(drawer).getByRole('button', { name: '알림 닫기' }));
    await waitFor(() => expect(drawer).not.toBeInTheDocument());
    await user.click(screen.getByRole('link', { name: '프로필로' }));
    const reopened = await openInbox(user);
    expect(within(reopened).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 0개',
    );
    await user.click(within(reopened).getByRole('button', { name: '전체' }));
    expect(within(reopened).getAllByRole('listitem')).toHaveLength(3);
  });

  it('keeps unread states after a failed mark-all and retries without removing items', async () => {
    const user = renderInbox(
      '/design-preview/explore?scenario=notification-error',
    );
    const drawer = await openInbox(user);
    await user.click(within(drawer).getByRole('button', { name: '모두 읽음' }));
    expect(within(drawer).getByRole('alert')).toHaveTextContent(
      '읽음 상태를 저장하지 못했어요. 다시 시도해 주세요.',
    );
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 3개',
    );
    expect(within(drawer).getAllByRole('listitem')).toHaveLength(3);
    await user.click(within(drawer).getByRole('button', { name: '다시 시도' }));
    expect(within(drawer).queryByRole('alert')).not.toBeInTheDocument();
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 0개',
    );
    expect(within(drawer).getAllByRole('listitem')).toHaveLength(3);
    expect(
      within(drawer).getByRole('button', { name: '모두 읽음' }),
    ).toBeDisabled();
  });

  it('prevents navigation after a failed single read and retries the same notification before navigating', async () => {
    const user = renderInbox(
      '/design-preview/explore?scenario=notification-error',
    );
    const drawer = await openInbox(user);
    const item = within(drawer).getByRole('link', {
      name: /김서연 님이 지원했어요/,
    });
    expect(item).toHaveAttribute('data-unread', 'true');
    await user.click(item);
    expect(
      screen.getByText(
        '현재 경로: /design-preview/explore?scenario=notification-error',
      ),
    ).toBeInTheDocument();
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 3개',
    );
    expect(item).toHaveAttribute('data-unread', 'true');
    await user.click(within(drawer).getByRole('button', { name: '다시 시도' }));
    await waitFor(() => expect(drawer).not.toBeInTheDocument());
    expect(
      screen.getByText('현재 경로: /design-preview/applicants/app-seoyeon'),
    ).toBeInTheDocument();
    const reopened = await openInbox(user);
    expect(within(reopened).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 2개',
    );
    expect(
      within(reopened).getByRole('link', { name: /김서연 님이 지원했어요/ }),
    ).not.toHaveAttribute('data-unread');
  });

  it('closes only the inbox on browser Back and keeps its underlying route and read history', async () => {
    const user = renderInbox('/design-preview/explore?tab=teams');
    const back = screen.getByRole('button', { name: '브라우저 뒤로' });
    const drawer = await openInbox(user);
    await user.click(within(drawer).getByRole('button', { name: '모두 읽음' }));
    fireEvent.click(back);
    await waitFor(() => expect(drawer).not.toBeInTheDocument());
    expect(
      screen.getByText('현재 경로: /design-preview/explore?tab=teams'),
    ).toBeInTheDocument();
    const reopened = await openInbox(user);
    expect(within(reopened).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 0개',
    );
    expect(within(reopened).getAllByRole('listitem')).toHaveLength(3);
  });

  it('records successful application transitions, preserves read history, and creates a new arrival after reapplication', async () => {
    render(
      <MemoryRouter initialEntries={['/design-preview/explore']}>
        <PreviewProvider>
          <Notifications />
          <ActivityControls />
        </PreviewProvider>
      </MemoryRouter>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '지원 준비' }));
    const initial = await openInbox(user);
    await user.click(
      within(initial).getByRole('button', { name: '모두 읽음' }),
    );
    await user.click(
      within(initial).getByRole('button', { name: '알림 닫기' }),
    );
    await waitFor(() => expect(initial).not.toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: '공개 팀에 지원' }));
    expect(
      screen.getByRole('button', { name: '알림, 읽지 않은 알림 1개' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '공개 팀에 지원' }));
    await user.click(screen.getByRole('button', { name: '내 팀에 지원 시도' }));
    expect(
      screen.getByRole('button', { name: '알림, 읽지 않은 알림 1개' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '방금 지원 취소' }));
    expect(
      screen.getByRole('button', { name: '알림, 읽지 않은 알림 2개' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '방금 지원 취소' }));
    await user.click(screen.getByRole('button', { name: '공개 팀에 지원' }));
    const history = await openInbox(user);
    expect(within(history).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 3개',
    );
    expect(within(history).getAllByRole('listitem')).toHaveLength(6);
    expect(
      within(history).getAllByRole('link', { name: /지원이 접수됐어요/ }),
    ).toHaveLength(2);
    expect(
      within(history).getByRole('link', { name: /지원이 취소됐어요/ }),
    ).toBeInTheDocument();
    expect(
      within(history).getByRole('link', { name: /지원한 팀에서 선발됐어요/ }),
    ).not.toHaveAttribute('data-unread');
  });

  it('shows the no-notifications state for an account with no relevant activity', async () => {
    const user = renderInbox('/design-preview/explore', {
      notifications: [],
      teams: [],
      applicants: [],
      applications: [],
    });
    const drawer = await openInbox(user);
    expect(
      within(drawer).getByRole('heading', { name: '아직 알림이 없어요' }),
    ).toBeInTheDocument();
    expect(
      within(drawer).getByRole('button', { name: '모두 읽음' }),
    ).toBeDisabled();
  });
});
