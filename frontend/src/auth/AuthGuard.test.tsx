import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ApiError, apiGet } from '../api/client.ts';
import { ADA, stubApi, stubSession } from '../test/api.ts';
import { currentUrl, renderApp } from '../test/render.tsx';

describe('AuthGuard', () => {
  it('sends a signed-out visitor home, with where they were going', async () => {
    stubSession(null);

    const { router } = renderApp('/orders?page=2');

    expect(
      await screen.findByRole('link', { name: 'Sign in with Google' }),
    ).toBeInTheDocument();
    expect(currentUrl(router)).toBe(
      `/?next=${encodeURIComponent('/orders?page=2')}`,
    );
  });

  it('renders the page for a signed-in user', async () => {
    stubSession(ADA);

    const { router } = renderApp('/orders');

    expect(
      await screen.findByRole('heading', { name: 'Orders' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Signed in as Ada Lovelace.')).toBeInTheDocument();
    expect(currentUrl(router)).toBe('/orders');
  });

  it('waits while the session loads, without showing the home page', () => {
    stubApi({
      'GET /api/auth/session/': () => new Promise<Response>(() => {}),
    });

    renderApp('/orders');

    expect(screen.getByRole('status')).toHaveTextContent('Loading…');
    expect(
      screen.queryByRole('link', { name: 'Sign in with Google' }),
    ).not.toBeInTheDocument();
  });

  it("says so when the session can't be loaded", async () => {
    stubApi({
      'GET /api/auth/session/': () => new Response(null, { status: 502 }),
    });

    renderApp('/orders');

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "ShipScope can't reach its server right now.",
    );
  });

  it('sends the user home when any request answers 401', async () => {
    stubApi({
      'GET /api/auth/session/': () => Response.json({ user: ADA }),
      'GET /api/example/': () => new Response(null, { status: 401 }),
    });
    const { router, queryClient } = renderApp('/settings');
    await screen.findByRole('heading', { name: 'Settings' });

    // Any query: the session ended on the server, for example in another tab.
    await expect(
      queryClient.fetchQuery({
        queryKey: ['example'],
        queryFn: () => apiGet('/example/'),
      }),
    ).rejects.toBeInstanceOf(ApiError);

    await waitFor(() => {
      expect(currentUrl(router)).toBe(
        `/?next=${encodeURIComponent('/settings')}`,
      );
    });
  });
});
