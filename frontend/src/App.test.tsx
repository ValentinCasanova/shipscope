import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App.tsx';
import { renderWithQueryClient } from './test/render.tsx';

describe('App', () => {
  it('renders the ShipScope heading', () => {
    // The health request never settles; HealthStatus has its own tests.
    vi.stubGlobal(
      'fetch',
      vi.fn(() => new Promise<Response>(() => {})),
    );

    renderWithQueryClient(<App />);

    expect(
      screen.getByRole('heading', { name: 'ShipScope' }),
    ).toBeInTheDocument();
  });
});
