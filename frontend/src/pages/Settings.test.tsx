import { fireEvent, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { ADA, stubApi, stubSession } from '../test/api.ts';
import { currentUrl, renderApp } from '../test/render.tsx';

const CONNECTED = { ...ADA, google_drive_connected: true };

afterEach(() => {
  document.cookie = 'csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT';
});

describe('Settings', () => {
  it('offers to connect Google Drive, and says what ShipScope can open', async () => {
    stubSession(ADA);

    renderApp('/settings');

    expect(
      await screen.findByRole('link', { name: 'Connect Google Drive' }),
    ).toHaveAttribute('href', '/api/auth/google/drive/connect/');
    expect(screen.getByText('Not connected.')).toBeInTheDocument();
    expect(
      screen.getByText(
        'ShipScope can open only the Sheets you pick, never the rest of your Drive.',
      ),
    ).toBeInTheDocument();
  });

  it('shows a connected Drive with a way to disconnect it', async () => {
    stubSession(CONNECTED);

    renderApp('/settings');

    expect(
      await screen.findByRole('button', { name: 'Disconnect' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Connected.')).toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Connect Google Drive' }),
    ).not.toBeInTheDocument();
  });

  it('disconnects after asking, with the CSRF header', async () => {
    document.cookie = 'csrftoken=the-token';
    const fetchMock = stubApi({
      'GET /api/auth/session/': () => Response.json({ user: CONNECTED }),
      'DELETE /api/auth/google/drive/': () =>
        new Response(null, { status: 204 }),
    });
    const { router } = renderApp('/settings');

    fireEvent.click(await screen.findByRole('button', { name: 'Disconnect' }));
    expect(fetchMock).not.toHaveBeenCalledWith(
      '/api/auth/google/drive/',
      expect.anything(),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Yes, disconnect' }));

    expect(
      await screen.findByRole('link', { name: 'Connect Google Drive' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(
      'Google Drive is disconnected.',
    );
    expect(currentUrl(router)).toBe('/settings?drive=disconnected');
    expect(fetchMock).toHaveBeenCalledWith('/api/auth/google/drive/', {
      method: 'DELETE',
      headers: { Accept: 'application/json', 'X-CSRFToken': 'the-token' },
    });
  });

  it('keeps Drive connected when the confirmation is cancelled', async () => {
    const fetchMock = stubSession(CONNECTED);
    renderApp('/settings');

    fireEvent.click(await screen.findByRole('button', { name: 'Disconnect' }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(
      screen.getByRole('button', { name: 'Disconnect' }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('says so when disconnecting fails', async () => {
    stubApi({
      'GET /api/auth/session/': () => Response.json({ user: CONNECTED }),
      'DELETE /api/auth/google/drive/': () =>
        new Response(null, { status: 502 }),
    });
    renderApp('/settings');

    fireEvent.click(await screen.findByRole('button', { name: 'Disconnect' }));
    fireEvent.click(screen.getByRole('button', { name: 'Yes, disconnect' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Disconnecting Google Drive didn't work.",
    );
    expect(screen.getByText('Connected.')).toBeInTheDocument();
  });

  it('confirms ?drive=connected', async () => {
    stubSession(CONNECTED);

    renderApp('/settings?drive=connected');

    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(
        'Google Drive is connected.',
      );
    });
  });

  it.each([
    ['cancelled', 'Connecting Google Drive was cancelled.'],
    ['wrong_account', 'That was another Google account.'],
    ['not_granted', "ShipScope didn't get access to your files."],
    ['failed', "Connecting Google Drive didn't work. Please try again."],
  ])('explains ?drive=%s', async (value, message) => {
    stubSession(ADA);

    renderApp(`/settings?drive=${value}`);

    expect(await screen.findByRole('alert')).toHaveTextContent(message);
    expect(
      screen.getByRole('link', { name: 'Connect Google Drive' }),
    ).toBeInTheDocument();
  });

  it('shows no message for an unknown ?drive value', async () => {
    stubSession(ADA);

    renderApp('/settings?drive=whatever');

    await screen.findByRole('link', { name: 'Connect Google Drive' });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toBeEmptyDOMElement();
  });
});
