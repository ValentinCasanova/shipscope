import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ADA, stubSession } from '../test/api.ts';
import { currentUrl, renderApp } from '../test/render.tsx';

function signInLink() {
  return screen.findByRole('link', { name: 'Sign in with Google' });
}

describe('Home', () => {
  it('describes ShipScope and links to the privacy policy', () => {
    stubSession(null);

    renderApp('/');

    expect(
      screen.getByRole('heading', { name: 'ShipScope' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'Compare shipping rates for the orders in your Google Sheet.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'Privacy policy' }),
    ).toHaveAttribute('href', '/privacy');
  });

  it('links the sign-in button to the start of Google sign-in', async () => {
    stubSession(null);

    renderApp('/');

    expect(await signInLink()).toHaveAttribute(
      'href',
      '/api/auth/google/login/',
    );
  });

  it('carries next into the sign-in link', async () => {
    stubSession(null);

    renderApp(`/?next=${encodeURIComponent('/orders?page=2')}`);

    expect(await signInLink()).toHaveAttribute(
      'href',
      `/api/auth/google/login/?next=${encodeURIComponent('/orders?page=2')}`,
    );
  });

  it.each([
    ['cancelled', 'Signing in was cancelled.'],
    ['failed', "Signing in didn't work. Please try again."],
  ])('explains ?signin=%s', async (value, message) => {
    stubSession(null);

    renderApp(`/?signin=${value}`);

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(await signInLink()).toBeInTheDocument();
  });

  it('shows no message for an unknown ?signin value', async () => {
    stubSession(null);

    renderApp('/?signin=whatever');

    await signInLink();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('links a signed-in visitor to their orders instead', async () => {
    stubSession(ADA);

    renderApp('/');

    expect(
      await screen.findByRole('link', { name: 'Go to your orders' }),
    ).toHaveAttribute('href', '/orders');
    expect(
      screen.queryByRole('link', { name: 'Sign in with Google' }),
    ).not.toBeInTheDocument();
  });
});

describe('the other public routes', () => {
  it('redirects /login to the home page, keeping the query string', async () => {
    stubSession(null);

    const { router } = renderApp('/login?next=%2Forders');

    await signInLink();
    expect(currentUrl(router)).toBe('/?next=%2Forders');
  });

  it('shows the privacy policy', () => {
    stubSession(null);

    renderApp('/privacy');

    expect(
      screen.getByRole('heading', { name: 'Privacy policy' }),
    ).toBeInTheDocument();
  });

  it('shows a not-found page for an unknown path', () => {
    stubSession(null);

    renderApp('/no-such-page');

    expect(
      screen.getByRole('heading', { name: 'Page not found' }),
    ).toBeInTheDocument();
  });
});
