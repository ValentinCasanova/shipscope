import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, apiDelete, apiGet, apiRequest } from './client.ts';

function setCsrfCookie(value: string | null) {
  document.cookie =
    value === null
      ? 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
      : `csrftoken=${value}`;
}

afterEach(() => {
  setCsrfCookie(null);
});

describe('apiGet', () => {
  it('requests JSON from /api on the same origin and returns the body', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(Response.json({ answer: 42 })),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiGet('/example/')).resolves.toEqual({ answer: 42 });
    expect(fetchMock).toHaveBeenCalledWith('/api/example/', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
  });

  it('throws an ApiError with the status for a non-2xx response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(null, { status: 404 }))),
    );

    const request = apiGet('/missing/');

    await expect(request).rejects.toBeInstanceOf(ApiError);
    await expect(request).rejects.toMatchObject({
      status: 404,
      message: 'GET /api/missing/ failed with HTTP 404',
    });
  });
});

describe('the CSRF header', () => {
  it.each(['GET', 'HEAD', 'OPTIONS'])(
    'is left out of %s requests',
    async (method) => {
      setCsrfCookie('the-token');
      const fetchMock = vi.fn(() => Promise.resolve(Response.json({})));
      vi.stubGlobal('fetch', fetchMock);

      await apiRequest(method, '/example/');

      expect(fetchMock).toHaveBeenCalledWith('/api/example/', {
        method,
        headers: { Accept: 'application/json' },
      });
    },
  );

  it.each(['POST', 'PUT', 'PATCH', 'DELETE'])(
    'is sent with %s requests, from the csrftoken cookie',
    async (method) => {
      setCsrfCookie('the-token');
      const fetchMock = vi.fn(() => Promise.resolve(Response.json({})));
      vi.stubGlobal('fetch', fetchMock);

      await apiRequest(method, '/example/');

      expect(fetchMock).toHaveBeenCalledWith('/api/example/', {
        method,
        headers: { Accept: 'application/json', 'X-CSRFToken': 'the-token' },
      });
    },
  );

  it('is left out when the cookie is missing', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(new Response(null, { status: 204 })),
    );
    vi.stubGlobal('fetch', fetchMock);

    await apiDelete('/example/');

    expect(fetchMock).toHaveBeenCalledWith('/api/example/', {
      method: 'DELETE',
      headers: { Accept: 'application/json' },
    });
  });
});

it('returns undefined for a 204', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response(null, { status: 204 }))),
  );

  await expect(apiDelete('/example/')).resolves.toBeUndefined();
});
