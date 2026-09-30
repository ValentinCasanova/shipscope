import { apiDelete } from './client.ts';

/**
 * Where "Connect Google Drive" leads: Django's start of Google's consent
 * screen, which asks for access to the files the user picks. Django comes back
 * to /settings?drive=<result>. It's a page navigation, not an API call.
 */
export const DRIVE_CONNECT_URL = '/api/auth/google/drive/connect/';

/** Revokes ShipScope's access at Google, and deletes the stored tokens. */
export function disconnectDrive(): Promise<void> {
  return apiDelete('/auth/google/drive/');
}
