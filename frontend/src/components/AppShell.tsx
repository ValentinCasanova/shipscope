import { NavLink, Outlet } from 'react-router';
import { useSession, useSignOut } from '../auth/useSession.ts';

/** The header and layout of the signed-in pages. AuthGuard renders it. */
function AppShell() {
  const session = useSession();
  const signOut = useSignOut();

  return (
    <>
      <header className="app-header">
        <NavLink to="/orders" className="app-name">
          ShipScope
        </NavLink>
        <nav aria-label="Main">
          <NavLink to="/orders">Orders</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <span className="user-name">{session.data?.user?.name}</span>
        <button
          type="button"
          onClick={() => signOut.mutate()}
          disabled={signOut.isPending}
        >
          Sign out
        </button>
      </header>
      {signOut.isError && (
        <p role="alert">Signing out didn&apos;t work. Please try again.</p>
      )}
      <main>
        <Outlet />
      </main>
    </>
  );
}

export default AppShell;
