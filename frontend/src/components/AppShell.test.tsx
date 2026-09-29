import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ADA, stubApi } from '../test/api.ts';
import { currentUrl, renderApp } from '../test/render.tsx';

afterEach(() => {
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

describe('AppShell', () => {
  it('shows the user and links to the signed-in pages', async () => {
    stubApi({ 'GET /api/auth/session/': () => Response.json({ user: ADA }) });

    renderApp('/orders');

    const nav = await screen.findByRole('navigation', { name: 'Main' });
    expect(nav).toHaveTextContent('OrdersSettings');
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
  });

  it('signs out with the CSRF header and ends on the home page', async () => {
    document.cookie = 'csrftoken=the-token';
    let signedIn = true;
    const fetchMock = stubApi({
      'GET /api/auth/session/': () =>
        Response.json({ user: signedIn ? ADA : null }),
      'DELETE /api/auth/session/': () => {
        signedIn = false;
        return new Response(null, { status: 204 });
      },
    });
    const { router } = renderApp('/orders');

    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }));

    await waitFor(() => {
      expect(currentUrl(router)).toBe('/');
    });
    expect(
      await screen.findByRole('link', { name: 'Sign in with Google' }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/session/', {
      method: 'DELETE',
      headers: { Accept: 'application/json', 'X-CSRFToken': 'the-token' },
    });
  });

  it('stays put and says so when signing out fails', async () => {
    stubApi({
      'GET /api/auth/session/': () => Response.json({ user: ADA }),
      'DELETE /api/auth/session/': () => new Response(null, { status: 403 }),
    });
    const { router } = renderApp('/orders');

    fireEvent.click(await screen.findByRole('button', { name: 'Sign out' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Signing out didn't work.",
    );
    expect(currentUrl(router)).toBe('/orders');
  });
});
