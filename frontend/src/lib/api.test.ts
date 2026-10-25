import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiRequest, resetCsrfToken } from './api';

afterEach(() => {
  vi.unstubAllGlobals();
  resetCsrfToken();
});

// docs/api/conventions.md#csrf-transport: 상태 변경 요청 전에 GET /auth/csrf로 토큰을 받습니다.
// 토큰 요청에는 발급 응답을, 나머지 요청에는 respond가 만든 응답을 돌려주는 fetch 대역입니다.
const CSRF = 'csrf-token-1';
function withCsrf(respond: () => Response | Promise<Response>) {
  const fetchMock = vi.fn<
    (url: string, init?: RequestInit) => Promise<Response>
  >((url) =>
    Promise.resolve(
      url.endsWith('/auth/csrf')
        ? Response.json({ data: { csrfToken: CSRF } })
        : respond(),
    ),
  );
  vi.stubGlobal('fetch', fetchMock);
  // 토큰 요청을 뺀 실제 호출만 봅니다.
  const calls = () =>
    fetchMock.mock.calls.filter(([url]) => !url.endsWith('/auth/csrf'));
  return { fetchMock, calls };
}

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
    const { calls } = withCsrf(() => Response.json({ data: {} }));

    await apiRequest('/auth/login', {
      method: 'POST',
      json: { loginId: 'dreamondemo', password: 'x'.repeat(15) },
    });
    const init = calls()[0]![1]!;
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
    withCsrf(() => new Response(null, { status: 204 }));

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
    const { calls } = withCsrf(() => Response.json({ id: 1 }));

    await apiRequest('/resource', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Request-ID': 'test' },
      body: '{"name":"example"}',
    });
    expect(calls()[0]).toEqual([
      '/api/v1/resource',
      expect.objectContaining({
        method: 'POST',
        headers: new Headers({
          Accept: 'application/json',
          'Content-Type': 'application/json',
          'X-Request-ID': 'test',
          'X-CSRF-Token': CSRF,
        }),
        body: '{"name":"example"}',
      }),
    ]);
  });
});

// docs/api/conventions.md#csrf-transport
describe('CSRF transport', () => {
  it('sends X-CSRF-Token with state changes only and reuses the token in memory', async () => {
    const { fetchMock } = withCsrf(() => Response.json({ data: {} }));
    await apiRequest('/me/profile');
    await apiRequest('/me/profile', { method: 'PUT', json: {} });
    await apiRequest('/teams', { method: 'POST', json: {} });
    const sent = fetchMock.mock.calls.map(([url, init]) => [
      url,
      init?.method ?? 'GET',
      new Headers(init?.headers).get('X-CSRF-Token'),
    ]);
    expect(sent).toEqual([
      ['/api/v1/me/profile', 'GET', null],
      ['/api/v1/auth/csrf', 'GET', null],
      ['/api/v1/me/profile', 'PUT', CSRF],
      ['/api/v1/teams', 'POST', CSRF],
    ]);
  });

  it('drops the token after a 403 without resending the request', async () => {
    let status = 403;
    const { fetchMock, calls } = withCsrf(() =>
      Response.json(
        { error: { code: 'FORBIDDEN', message: '거부' }, requestId: 'r' },
        { status },
      ),
    );
    await expect(
      apiRequest('/teams', { method: 'POST', json: {} }),
    ).rejects.toMatchObject({ status: 403 });
    expect(calls()).toHaveLength(1);
    status = 200;
    await apiRequest('/teams', { method: 'POST', json: {} });
    // 실패 뒤 다음 요청은 토큰을 다시 받습니다.
    expect(
      fetchMock.mock.calls.filter(([url]) => url.endsWith('/auth/csrf')),
    ).toHaveLength(2);
  });
});
