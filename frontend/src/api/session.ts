import { apiDelete, apiGet } from './client.ts';

/** The signed-in user, as GET /api/auth/session/ returns it (accounts/views.py). */
export interface SessionUser {
  id: number;
  email: string;
  name: string;
  google_drive_connected: boolean;
}

export interface SessionResponse {
  user: SessionUser | null;
}

export const sessionQueryKey = ['session'] as const;

/** Who is signed in. Answers {"user": null} when nobody is, never 401. */
export function getSession(): Promise<SessionResponse> {
  return apiGet<SessionResponse>('/auth/session/');
}

/** Ends the session on the server. */
export function signOut(): Promise<void> {
  return apiDelete('/auth/session/');
}

/**
 * Where the sign-in button leads: Django's start of Google's flow, which comes
 * back to `next` once signed in. It's a page navigation, not an API call.
 */
export function signInUrl(next?: string | null): string {
  const url = '/api/auth/google/login/';
  return next ? `${url}?${new URLSearchParams({ next }).toString()}` : url;
}
