import { MutationCache, QueryCache, QueryClient } from '@tanstack/react-query';
import { isUnauthorized } from './client.ts';
import { sessionQueryKey, type SessionResponse } from './session.ts';

/**
 * The app's QueryClient. A 401 from any query or mutation means the session has
 * ended on the server, for example after two weeks or a sign-out in another tab.
 * The cached session then becomes signed out, and AuthGuard sends the user home.
 */
export function createQueryClient(
  options: { retry?: false } = {},
): QueryClient {
  const onError = (error: unknown) => {
    if (isUnauthorized(error)) {
      queryClient.setQueryData<SessionResponse>(sessionQueryKey, {
        user: null,
      });
    }
  };
  const queryClient: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      queries: {
        // Retrying can't turn a 401 into a success.
        retry: (failureCount, error) =>
          options.retry !== false && !isUnauthorized(error) && failureCount < 3,
      },
    },
  });
  return queryClient;
}
