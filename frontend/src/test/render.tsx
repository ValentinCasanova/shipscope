import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';

/**
 * Renders `ui` with its own QueryClient, so tests never share cached data. Failed
 * queries aren't retried: TanStack Query's default of 3 retries with backoff takes
 * about 7 seconds, far longer than Testing Library waits for an element to appear.
 */
export function renderWithQueryClient(ui: ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(ui, {
    wrapper: ({ children }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  });
}
