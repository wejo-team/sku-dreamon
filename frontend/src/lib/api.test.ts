import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest } from './api';

afterEach(() => vi.unstubAllGlobals());

describe('apiRequest', () => {
  it('requests the configured API base and returns JSON', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(Response.json({ status: 'ok' }));
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiRequest('/health')).resolves.toEqual({ status: 'ok' });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/health', {
      headers: new Headers({ Accept: 'application/json' }),
    });
  });

  it('returns undefined for a 204 without trying to parse JSON', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(null, { status: 204 })),
    );

    await expect(
      apiRequest('/resource', { method: 'DELETE' }),
    ).resolves.toBeUndefined();
  });

  it('rejects HTTP errors and preserves JSON error details', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          Response.json({ detail: 'Forbidden' }, { status: 403 }),
        ),
    );

    await expect(apiRequest('/private')).rejects.toMatchObject({
      name: 'ApiError',
      status: 403,
      body: { detail: 'Forbidden' },
    });
  });

  it('handles a proxy returning a non-JSON error body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('Bad Gateway', { status: 502 })),
    );

    await expect(apiRequest('/health')).rejects.toEqual(
      new ApiError(502, 'Bad Gateway'),
    );
  });

  it('propagates network failures', async () => {
    const error = new TypeError('Failed to fetch');
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(error));

    await expect(apiRequest('/health')).rejects.toBe(error);
  });

  it('forwards the abort signal and preserves cancellation', async () => {
    const controller = new AbortController();
    const error = new DOMException('Aborted', 'AbortError');
    controller.abort();
    const fetchMock = vi.fn().mockRejectedValue(error);
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      apiRequest('/health', { signal: controller.signal }),
    ).rejects.toBe(error);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/health',
      expect.objectContaining({ signal: controller.signal }),
    );
  });

  it('preserves caller headers and request options', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ id: 1 }));
    vi.stubGlobal('fetch', fetchMock);

    await apiRequest('/resource', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'test' },
      body: '{"name":"example"}',
    });
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/resource',
      expect.objectContaining({
        method: 'POST',
        headers: new Headers({
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-Request-ID': 'test',
        }),
        body: '{"name":"example"}',
      }),
    );
  });
});
