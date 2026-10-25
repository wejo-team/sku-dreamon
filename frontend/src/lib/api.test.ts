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
    // docs/api/conventions.md#session-auth: 세션은 브라우저 쿠키로 전달합니다.
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/health', {
      headers: new Headers({ Accept: 'application/json' }),
      credentials: 'include',
    });
  });

  it('serializes a JSON body with its content type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ data: {} }));
    vi.stubGlobal('fetch', fetchMock);

    await apiRequest('/auth/login', {
      method: 'POST',
      json: { loginId: 'dreamondemo', password: 'x'.repeat(15) },
    });
    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect(init.body).toBe(
      JSON.stringify({ loginId: 'dreamondemo', password: 'x'.repeat(15) }),
    );
    expect(new Headers(init.headers).get('Content-Type')).toBe(
      'application/json',
    );
  });

  it('exposes the business error code and request ID from the common Error body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        Response.json(
          {
            error: {
              code: 'VERSION_CONFLICT',
              message: '정보가 변경되었습니다.',
            },
            requestId: 'request-1',
          },
          { status: 409 },
        ),
      ),
    );

    await expect(apiRequest('/me/profile')).rejects.toMatchObject({
      status: 409,
      code: 'VERSION_CONFLICT',
      requestId: 'request-1',
      issues: [],
    });
  });

  it('exposes validation issues from a 422 body', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        Response.json(
          {
            detail: [
              {
                loc: ['body', 'loginId'],
                msg: '형식 오류',
                type: 'value_error',
              },
            ],
          },
          { status: 422 },
        ),
      ),
    );

    await expect(apiRequest('/accounts')).rejects.toMatchObject({
      status: 422,
      code: null,
      issues: [
        { loc: ['body', 'loginId'], msg: '형식 오류', type: 'value_error' },
      ],
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
