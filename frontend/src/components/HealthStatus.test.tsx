import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { renderWithQueryClient } from '../test/render.tsx';
import HealthStatus from './HealthStatus.tsx';

describe('HealthStatus', () => {
  it('shows a loading message while the request is in flight', () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => {})),
    );

    renderWithQueryClient(<HealthStatus />);

    expect(screen.getByRole('status')).toHaveTextContent('Checking the API…');
  });

  it('shows the API and database status from the response', async () => {
    const fetchMock = vi.fn(() =>
      Promise.resolve(Response.json({ status: 'ok', database: 'unavailable' })),
    );
    vi.stubGlobal('fetch', fetchMock);

    renderWithQueryClient(<HealthStatus />);

    const status = screen.getByRole('status');
    expect(await within(status).findByText('API: ok')).toBeInTheDocument();
    expect(
      within(status).getByText('Database: unavailable'),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith('/api/health/', expect.anything());
  });

  it('shows an error when the API responds with an error status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(null, { status: 502 }))),
    );

    renderWithQueryClient(<HealthStatus />);

    expect(
      await within(screen.getByRole('status')).findByText(
        'API unavailable: GET /api/health/ failed with HTTP 502',
      ),
    ).toBeInTheDocument();
  });
});
