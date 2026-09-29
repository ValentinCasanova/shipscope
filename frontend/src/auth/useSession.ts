import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router';
import {
  getSession,
  sessionQueryKey,
  signOut,
  type SessionResponse,
} from '../api/session.ts';

/**
 * Who is signed in. Signing in happens outside the app (a full page load back
 * from Google), and a 401 marks the cache signed out (queryClient.ts), so the
 * answer rarely changes while the app runs.
 */
export function useSession() {
  return useQuery({
    queryKey: sessionQueryKey,
    queryFn: getSession,
    staleTime: 5 * 60 * 1000,
  });
}

/** Signs out on the server, forgets every cached answer, and goes home. */
export function useSignOut() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  return useMutation({
    mutationFn: signOut,
    onSuccess: async () => {
      // Leave the signed-in page first: while it's shown, a signed-out session
      // would make AuthGuard send the user home with ?next= back to it.
      await navigate('/');
      queryClient.removeQueries();
      queryClient.setQueryData<SessionResponse>(sessionQueryKey, {
        user: null,
      });
    },
  });
}
