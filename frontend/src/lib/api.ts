const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(
  /\/$/,
  '',
);

export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown) {
    super(`API request failed (${status})`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }
}

export async function apiRequest(
  path: string,
  options: RequestInit = {},
): Promise<unknown> {
  const headers = new Headers(options.headers);
  if (!headers.has('Accept')) headers.set('Accept', 'application/json');

  const response = await fetch(`${baseUrl}/${path.replace(/^\//, '')}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const text = await response.text();
    let body: unknown = text;
    try {
      body = JSON.parse(text);
    } catch {
      // Proxy errors may return HTML or text instead of the API's JSON format.
    }
    throw new ApiError(response.status, body);
  }

  if (response.status === 204) return undefined;

  const body: unknown = await response.json();
  return body;
}
