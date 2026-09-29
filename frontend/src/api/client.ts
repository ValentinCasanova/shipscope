/** Thrown when the API responds with a status outside the 2xx range. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/** True for the API's answer to a signed-out request. */
export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

// Methods Django's CSRF check skips. Every other method must send the token.
const SAFE_METHODS = new Set(['GET', 'HEAD', 'OPTIONS', 'TRACE']);

/**
 * The value of the csrftoken cookie, which GET /api/auth/session/ sets. Django
 * compares it with the X-CSRFToken header, which only a page on this origin can
 * read the cookie to send.
 */
export function csrfToken(): string | undefined {
  return document.cookie
    .split('; ')
    .find((cookie) => cookie.startsWith('csrftoken='))
    ?.slice('csrftoken='.length);
}

/**
 * Sends a request to the API and returns the JSON body, or undefined for a 204.
 *
 * `path` is relative to /api on the page's own origin, so requests are never
 * cross-origin: the Vite dev server forwards /api/ to Django, and in AWS
 * CloudFront does. The browser sends the session cookie with every request.
 */
export async function apiRequest<T>(method: string, path: string): Promise<T> {
  const url = `/api${path}`;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (!SAFE_METHODS.has(method)) {
    const token = csrfToken();
    if (token) {
      headers['X-CSRFToken'] = token;
    }
  }
  const response = await fetch(url, { method, headers });
  if (!response.ok) {
    throw new ApiError(
      `${method} ${url} failed with HTTP ${response.status}`,
      response.status,
    );
  }
  if (response.status === 204) {
    return undefined as T;
  }
  // Not validated at runtime: T describes the body the endpoint promises.
  const body: unknown = await response.json();
  return body as T;
}

export function apiGet<T>(path: string): Promise<T> {
  return apiRequest<T>('GET', path);
}

export function apiDelete(path: string): Promise<void> {
  return apiRequest<void>('DELETE', path);
}
