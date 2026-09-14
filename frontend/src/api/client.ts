/** Thrown when the API responds with a status outside the 2xx range. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/**
 * Sends a GET request to the API and returns the JSON body.
 *
 * `path` is relative to /api on the page's own origin, so requests are never
 * cross-origin: the Vite dev server forwards /api/ to Django, and in production
 * CloudFront will route it to the backend.
 */
export async function apiGet<T>(path: string): Promise<T> {
  const url = `/api${path}`;
  const response = await fetch(url, {
    headers: { Accept: 'application/json' },
  });
  if (!response.ok) {
    throw new ApiError(
      `GET ${url} failed with HTTP ${response.status}`,
      response.status,
    );
  }
  // Not validated at runtime: T describes the body the endpoint promises.
  const body: unknown = await response.json();
  return body as T;
}
