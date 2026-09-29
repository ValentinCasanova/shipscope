import { useSession } from '../auth/useSession.ts';

/** The orders page. For now it only confirms who is signed in. */
function Orders() {
  const session = useSession();

  return (
    <>
      <h1>Orders</h1>
      <p>Signed in as {session.data?.user?.name}.</p>
      <p>Your orders will appear here once you can connect a Google Sheet.</p>
    </>
  );
}

export default Orders;
