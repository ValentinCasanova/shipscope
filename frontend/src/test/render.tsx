import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render } from '@testing-library/react';
import type { ReactElement } from 'react';
import { createMemoryRouter } from 'react-router';
import { RouterProvider } from 'react-router/dom';
import { createQueryClient } from '../api/queryClient.ts';
import { routes } from '../router.tsx';

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

/**
 * Renders the whole app at `path`, with the real routes in a memory router and
 * the app's QueryClient, without retries. Returns the router, whose state shows
 * where the app ended up, and the QueryClient.
 */
export function renderApp(path: string) {
  const queryClient = createQueryClient({ retry: false });
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { router, queryClient };
}

/** Where the app is now, as path and query string. */
export function currentUrl(router: ReturnType<typeof createMemoryRouter>) {
  const { pathname, search } = router.state.location;
  return `${pathname}${search}`;
}
