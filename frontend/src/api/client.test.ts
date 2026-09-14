import { describe, expect, it, vi } from 'vitest';
import { ApiError, apiGet } from './client.ts';

describe('apiGet', () => {
  it('requests JSON from /api on the same origin and returns the body', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(Response.json({ answer: 42 })),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(apiGet('/example/')).resolves.toEqual({ answer: 42 });
    expect(fetchMock).toHaveBeenCalledWith('/api/example/', {
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
