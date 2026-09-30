import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { DRIVE_CONNECT_URL, disconnectDrive } from '../api/drive.ts';
import { sessionQueryKey, type SessionResponse } from '../api/session.ts';
import { useSession } from '../auth/useSession.ts';

// What ?drive= reports: Django's callback after connecting Google Drive, or
// this page after disconnecting it.
const DRIVE_NOTICES: Record<string, string> = {
  connected: 'Google Drive is connected.',
  disconnected: 'Google Drive is disconnected.',
};
const DRIVE_ALERTS: Record<string, string> = {
  cancelled: 'Connecting Google Drive was cancelled.',
  wrong_account:
    'That was another Google account. Connect the account you sign in with.',
  not_granted:
    "ShipScope didn't get access to your files. Connect again, and leave the box for Google Drive ticked.",
  failed: "Connecting Google Drive didn't work. Please try again.",
};

/**
 * The settings page: connecting Google Drive, which reading a Sheet needs, and
 * disconnecting it.
 */
function Settings() {
  const session = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [confirming, setConfirming] = useState(false);
  const queryClient = useQueryClient();
  const disconnect = useMutation({
    mutationFn: disconnectDrive,
    onSuccess: () => {
      queryClient.setQueryData<SessionResponse>(sessionQueryKey, (old) =>
        old?.user
          ? { user: { ...old.user, google_drive_connected: false } }
          : old,
      );
      setConfirming(false);
      setSearchParams({ drive: 'disconnected' }, { replace: true });
    },
  });
  const connected = session.data?.user?.google_drive_connected ?? false;
  const result = searchParams.get('drive') ?? '';
  const notice = DRIVE_NOTICES[result];
  const alert = DRIVE_ALERTS[result];

  return (
    <>
      <h1>Settings</h1>
      <section aria-labelledby="drive-heading">
        <h2 id="drive-heading">Google Drive</h2>
        <p>
          ShipScope can open only the Sheets you pick, never the rest of your
          Drive.
        </p>
        {/* Stays mounted while its content changes, so screen readers announce
            the notice that disconnecting adds. */}
        <div role="status">{notice && <p className="notice">{notice}</p>}</div>
        {alert && <p role="alert">{alert}</p>}
        {connected ? (
          <>
            <p>Connected.</p>
            {confirming ? (
              <div className="confirm">
                <p>
                  Disconnect Google Drive? ShipScope won&apos;t be able to open
                  your Sheets until you connect it again.
                </p>
                <button
                  type="button"
                  onClick={() => disconnect.mutate()}
                  disabled={disconnect.isPending}
                >
                  Yes, disconnect
                </button>{' '}
                <button type="button" onClick={() => setConfirming(false)}>
                  Cancel
                </button>
              </div>
            ) : (
              <button type="button" onClick={() => setConfirming(true)}>
                Disconnect
              </button>
            )}
            {disconnect.isError && (
              <p role="alert">
                Disconnecting Google Drive didn&apos;t work. Please try again.
              </p>
            )}
          </>
        ) : (
          <>
            <p>Not connected.</p>
            <a href={DRIVE_CONNECT_URL}>Connect Google Drive</a>
          </>
        )}
      </section>
    </>
  );
}

export default Settings;
