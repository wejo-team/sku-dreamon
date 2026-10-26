import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { setupUser } from '@/test/user';
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation, useNavigate } from 'react-router';
import { describe, expect, it } from 'vitest';
import { Notifications } from '@/features/notifications/NotificationInbox';
import {
  myApplicationsQueryOptions,
  useApply,
  useCancelApplication,
} from '@/features/applications/queries';
import type { DemoDatabase } from '@/features/demo/fixtures';
import {
  demoIds,
  ME,
  recordsWithMyProfile,
  renderWithApi,
  settled,
} from '@/test/render';

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
      <Link to="/profile">프로필로</Link>
    </>
  );
}

function RoutedInbox() {
  const location = useLocation();
  return <Notifications key={location.pathname} />;
}

// 지원·취소를 실제 API(목업 서버)로 요청하는 테스트 조작 버튼
function ActivityControls() {
  const apply = useApply();
  const cancel = useCancelApplication();
  const mine = useQuery(myApplicationsQueryOptions()).data?.data ?? [];
  const applyTo = (teamId: string, roleCode: string) =>
    apply.mutate({
      teamId,
      body: { requestId: crypto.randomUUID(), roleCode, message: null },
    });
  return (
    <>
      <button onClick={() => applyTo(demoIds.teams.makers, 'planning')}>
        공개 팀에 지원
      </button>
      <button onClick={() => applyTo(demoIds.teams.greenwave, 'development')}>
        내 팀에 지원 시도
      </button>
      <button
        onClick={() => {
          const latest = mine.find(
            ({ application }) =>
              application.teamId === demoIds.teams.makers &&
              application.status !== 'canceled',
          )?.application;
          if (latest)
            cancel.mutate({
              applicationId: latest.id,
              expectedVersion: latest.version,
            });
        }}
      >
        방금 지원 취소
      </button>
    </>
  );
}

async function renderInbox(
  path = '/explore',
  options: { signedIn?: boolean; db?: DemoDatabase } = {},
) {
  const { client } = renderWithApi(
    <>
      <RoutedInbox />
      <Navigation />
    </>,
    { path, signedIn: options.signedIn ?? true, db: options.db },
  );
  await screen.findByRole('button', { name: /^알림(?:,|$)/ });
  await settled(client);
  return { user: setupUser(), client };
}

async function openInbox(user: ReturnType<typeof setupUser>) {
  await user.click(screen.getByRole('button', { name: /^알림(?:,|$)/ }));
  return screen.findByRole('dialog', { name: '알림' });
}

describe('official reference notifications', () => {
  it('shows no account notification or unread count to guests and preserves the login destination', async () => {
    const { user } = await renderInbox('/explore?tab=teams', {
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
    ).toHaveAttribute('href', '/login?returnTo=%2Fexplore%3Ftab%3Dteams');
  });

  it('marks all read without deleting notifications and keeps that state across normal routes', async () => {
    const { user } = await renderInbox();
    const drawer = await openInbox(user);
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 3개',
    );
    expect(within(drawer).getAllByRole('listitem')).toHaveLength(3);
    await user.click(within(drawer).getByRole('button', { name: '모두 읽음' }));
    await waitFor(() =>
      expect(within(drawer).getByRole('status')).toHaveTextContent(
        '읽지 않은 알림 0개',
      ),
    );
    expect(within(drawer).getAllByRole('listitem')).toHaveLength(3);
    await user.click(
      within(drawer).getByRole('button', { name: /읽지 않음 0/ }),
    );
    expect(
      await within(drawer).findByRole('heading', {
        name: '모든 알림을 확인했어요',
      }),
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
    const { user } = await renderInbox('/explore?scenario=notification-error');
    const drawer = await openInbox(user);
    await user.click(within(drawer).getByRole('button', { name: '모두 읽음' }));
    expect(await within(drawer).findByRole('alert')).toHaveTextContent(
      '읽음 상태를 저장하지 못했어요. 다시 시도해 주세요.',
    );
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 3개',
    );
    expect(within(drawer).getAllByRole('listitem')).toHaveLength(3);
    await user.click(within(drawer).getByRole('button', { name: '다시 시도' }));
    await waitFor(() =>
      expect(within(drawer).queryByRole('alert')).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(within(drawer).getByRole('status')).toHaveTextContent(
        '읽지 않은 알림 0개',
      ),
    );
    expect(within(drawer).getAllByRole('listitem')).toHaveLength(3);
    expect(
      within(drawer).getByRole('button', { name: '모두 읽음' }),
    ).toBeDisabled();
  });

  it('prevents navigation after a failed single read and retries the same notification before navigating', async () => {
    const { user } = await renderInbox('/explore?scenario=notification-error');
    const drawer = await openInbox(user);
    const item = within(drawer).getByRole('link', {
      name: /김서연 님이 지원했어요/,
    });
    expect(item).toHaveAttribute('data-unread', 'true');
    await user.click(item);
    await within(drawer).findByRole('alert');
    expect(
      screen.getByText('현재 경로: /explore?scenario=notification-error'),
    ).toBeInTheDocument();
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 3개',
    );
    expect(item).toHaveAttribute('data-unread', 'true');
    await user.click(within(drawer).getByRole('button', { name: '다시 시도' }));
    await waitFor(() => expect(drawer).not.toBeInTheDocument());
    expect(
      screen.getByText(
        `현재 경로: /applicants/${demoIds.applications.seoyeon}`,
      ),
    ).toBeInTheDocument();
    const reopened = await openInbox(user);
    await waitFor(() =>
      expect(within(reopened).getByRole('status')).toHaveTextContent(
        '읽지 않은 알림 2개',
      ),
    );
    expect(
      within(reopened).getByRole('link', { name: /김서연 님이 지원했어요/ }),
    ).not.toHaveAttribute('data-unread');
  });

  it('closes only the inbox on browser Back and keeps its underlying route and read history', async () => {
    const { user, client } = await renderInbox('/explore?tab=teams');
    const back = screen.getByRole('button', { name: '브라우저 뒤로' });
    const drawer = await openInbox(user);
    await user.click(within(drawer).getByRole('button', { name: '모두 읽음' }));
    await settled(client);
    fireEvent.click(back);
    await waitFor(() => expect(drawer).not.toBeInTheDocument());
    expect(
      screen.getByText('현재 경로: /explore?tab=teams'),
    ).toBeInTheDocument();
    const reopened = await openInbox(user);
    expect(within(reopened).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 0개',
    );
    expect(within(reopened).getAllByRole('listitem')).toHaveLength(3);
  });

  it('records successful application transitions, preserves read history, and creates a new arrival after reapplication', async () => {
    // 공개 프로필 상태의 본인이 지원·취소를 실제 API로 반복합니다.
    const { client } = renderWithApi(
      <>
        <Notifications />
        <ActivityControls />
      </>,
      {
        path: '/explore',
        signedIn: true,
        db: recordsWithMyProfile({ isPublic: true }),
      },
    );
    const user = setupUser();
    await screen.findByRole('button', { name: /^알림(?:,|$)/ });
    await settled(client);
    const initial = await openInbox(user);
    await user.click(
      within(initial).getByRole('button', { name: '모두 읽음' }),
    );
    await settled(client);
    await user.click(
      within(initial).getByRole('button', { name: '알림 닫기' }),
    );
    await waitFor(() => expect(initial).not.toBeInTheDocument());
    await user.click(screen.getByRole('button', { name: '공개 팀에 지원' }));
    await settled(client);
    expect(
      screen.getByRole('button', { name: '알림, 읽지 않은 알림 1개' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '공개 팀에 지원' }));
    await settled(client);
    await user.click(screen.getByRole('button', { name: '내 팀에 지원 시도' }));
    await settled(client);
    expect(
      screen.getByRole('button', { name: '알림, 읽지 않은 알림 1개' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '방금 지원 취소' }));
    await settled(client);
    expect(
      screen.getByRole('button', { name: '알림, 읽지 않은 알림 2개' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '방금 지원 취소' }));
    await settled(client);
    await user.click(screen.getByRole('button', { name: '공개 팀에 지원' }));
    await settled(client);
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
    const db = recordsWithMyProfile({});
    const { user } = await renderInbox('/explore', {
      db: { ...db, notifications: [] },
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

// Codex 리뷰 P2: 첫 페이지 밖의 미읽음도 서버의 전체 미읽음 수(unreadCount)와 unreadOnly 목록으로 보여 줍니다.
describe('notifications beyond the first page', () => {
  it('counts, filters and reads an older unread notification after 100 newer read ones', async () => {
    const records = recordsWithMyProfile({});
    const mine = records.notifications.filter(
      (item) => item.recipientAccountId === ME,
    );
    const base = mine[0]!;
    const id = (index: number) =>
      `00000000-0000-4000-8000-${index.toString(16).padStart(12, '0')}`;
    // 최신 100건은 읽음, 그보다 오래된 1건만 미읽음
    const newer = Array.from({ length: 100 }, (_, index) => ({
      ...base,
      id: id(index + 1),
      title: `읽은 알림 ${index}`,
      occurredAt: new Date(Date.UTC(2026, 9, 17) + index * 60_000)
        .toISOString()
        .replace('.000Z', 'Z'),
      readAt: '2026-10-18T08:00:00Z',
    }));
    const older = {
      ...base,
      id: id(101),
      title: '오래된 미읽음 알림',
      occurredAt: '2026-10-01T00:00:00Z',
      readAt: null,
    };
    const { user } = await renderInbox('/explore', {
      db: {
        ...records,
        notifications: [
          ...records.notifications.filter(
            (item) => item.recipientAccountId !== ME,
          ),
          ...newer,
          older,
        ],
      },
    });
    expect(
      screen.getByRole('button', { name: '알림, 읽지 않은 알림 1개' }),
    ).toBeInTheDocument();
    const drawer = await openInbox(user);
    expect(within(drawer).getByRole('status')).toHaveTextContent(
      '읽지 않은 알림 1개',
    );
    await user.click(
      within(drawer).getByRole('button', { name: /읽지 않음 1/ }),
    );
    expect(
      await within(drawer).findByRole('link', { name: /오래된 미읽음 알림/ }),
    ).toHaveAttribute('data-unread');
    await user.click(within(drawer).getByRole('button', { name: '모두 읽음' }));
    await waitFor(() =>
      expect(within(drawer).getByRole('status')).toHaveTextContent(
        '읽지 않은 알림 0개',
      ),
    );
    expect(
      await within(drawer).findByRole('heading', {
        name: '모든 알림을 확인했어요',
      }),
    ).toBeInTheDocument();
  });
});
