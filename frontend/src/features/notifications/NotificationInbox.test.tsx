import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation, useNavigate } from 'react-router';
import { describe, expect, it } from 'vitest';
import { NotificationInbox } from './NotificationInbox';

function Navigation() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <>
      <p>현재 경로: {location.pathname}</p>
      <button type="button" onClick={() => navigate(-1)}>
        브라우저 뒤로
      </button>
    </>
  );
}

function renderInbox() {
  render(
    <MemoryRouter initialEntries={['/workspace', '/profile']} initialIndex={1}>
      <NotificationInbox />
      <Navigation />
    </MemoryRouter>,
  );
}

describe('NotificationInbox', () => {
  it('뒤로 가기는 경로를 유지한 채 알림함만 닫는다', async () => {
    const user = userEvent.setup();
    renderInbox();

    await user.click(screen.getByRole('button', { name: /^알림/ }));
    expect(
      await screen.findByRole('dialog', { name: '알림함' }),
    ).toBeInTheDocument();
    expect(screen.getByText('현재 경로: /profile')).toBeInTheDocument();

    // 모달이 열린 동안 배경은 inert 처리되므로 history 이동을 직접 호출한다.
    const back = screen.getByRole('button', {
      name: '브라우저 뒤로',
      hidden: true,
    });
    back.click();

    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    );
    expect(screen.getByText('현재 경로: /profile')).toBeInTheDocument();
  });

  it('닫기 버튼으로 닫아도 경로가 바뀌지 않는다', async () => {
    const user = userEvent.setup();
    renderInbox();

    await user.click(screen.getByRole('button', { name: /^알림/ }));
    await user.click(await screen.findByRole('button', { name: '알림 닫기' }));

    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    );
    expect(screen.getByText('현재 경로: /profile')).toBeInTheDocument();
  });
});
