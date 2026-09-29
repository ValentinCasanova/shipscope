import { Navigate, Outlet, useLocation } from 'react-router';
import { useSession } from './useSession.ts';

/**
 * Renders the signed-in routes below it only for a signed-in user. Everyone
 * else goes to the home page, with ?next= set to where they were going, so
 * signing in brings them back there.
 *
 * The API refuses signed-out requests on its own (401). This guard only keeps
 * signed-out visitors from seeing pages that can't work for them.
 */
function AuthGuard() {
  const session = useSession();
  const location = useLocation();

  if (session.isPending) {
    // Not the home page: a signed-in user would see it flash before their page.
    return <p role="status">Loading…</p>;
  }
  if (session.isError) {
    return (
      <p role="alert">
        ShipScope can&apos;t reach its server right now. Reload the page to try
        again.
      </p>
    );
  }
  if (!session.data.user) {
    const next = `${location.pathname}${location.search}`;
    return (
      <Navigate
        to={{ pathname: '/', search: new URLSearchParams({ next }).toString() }}
        replace
      />
    );
  }
  return <Outlet />;
}

export default AuthGuard;
