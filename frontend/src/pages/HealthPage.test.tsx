import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HealthPage } from './HealthPage';

const clients: QueryClient[] = [];

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
  clients.push(client);
  return render(
    <QueryClientProvider client={client}>
      <HealthPage />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  clients.splice(0).forEach((client) => client.clear());
  vi.unstubAllGlobals();
});

describe('HealthPage', () => {
  it('shows pending state before reporting a successful API response', async () => {
    let complete: (response: Response) => void = () => {
      throw new Error('The request has not started');
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(
        () =>
          new Promise<Response>((resolve) => {
            complete = resolve;
          }),
      ),
    );
    renderPage();

    expect(screen.getByRole('status')).toHaveTextContent('연결 확인 중');
    expect(screen.getByRole('button', { name: '확인 중' })).toBeDisabled();
    complete(Response.json({ status: 'ok' }));

    expect(
      await screen.findByText('API 서버가 응답했어요'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('데이터베이스 연결은 별도로 확인해야 합니다.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '다시 확인' })).toBeEnabled();
  });

  it('shows a server error and lets the user retry successfully', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('Unavailable', { status: 503 }))
      .mockResolvedValueOnce(Response.json({ status: 'ok' }));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    renderPage();

    expect(
      await screen.findByText('API 연결을 확인하지 못했어요'),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await user.click(screen.getByRole('button', { name: '다시 확인' }));

    expect(
      await screen.findByText('API 서버가 응답했어요'),
    ).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it('shows a network error with a usable retry button', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
    );
    renderPage();

    expect(
      await screen.findByText('API 연결을 확인하지 못했어요'),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '다시 확인' })).toBeEnabled();
  });

  it('does not report a successful connection for an unexpected API contract', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(Response.json({ status: 'degraded' })),
    );
    renderPage();

    expect(
      await screen.findByText('API 연결을 확인하지 못했어요'),
    ).toBeInTheDocument();
    expect(screen.queryByText('API 서버가 응답했어요')).not.toBeInTheDocument();
  });
});
