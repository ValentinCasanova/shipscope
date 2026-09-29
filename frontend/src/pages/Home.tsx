import { Link, useSearchParams } from 'react-router';
import { useSession } from '../auth/useSession.ts';
import HealthStatus from '../components/HealthStatus.tsx';
import SignInButton from '../components/SignInButton.tsx';

// Where Django's callback sends the browser when signing in didn't finish.
const SIGN_IN_MESSAGES: Record<string, string> = {
  cancelled: 'Signing in was cancelled.',
  failed: "Signing in didn't work. Please try again.",
};

/**
 * The public home page: what ShipScope does, and the way in. Google's brand
 * verification wants a homepage that describes the app, not only a sign-in
 * button.
 */
function Home() {
  const [searchParams] = useSearchParams();
  const session = useSession();
  const next = searchParams.get('next');
  const message = SIGN_IN_MESSAGES[searchParams.get('signin') ?? ''];
  const user = session.data?.user;

  return (
    <>
      <main className="home">
        <h1>ShipScope</h1>
        <p className="lead">
          Compare shipping rates for the orders in your Google Sheet.
        </p>
        <p>
          Connect a Sheet of orders, and ShipScope fetches live rates from the
          major carriers for each one, so you can pick the cheapest or fastest
          option. It also flags orders that look unusual, such as a missing
          address line or a weight far outside the rest, before you buy a label.
        </p>
        {message && <p role="alert">{message}</p>}
        {/* Nothing while the session loads, so the button doesn't flash for a
            signed-in visitor. */}
        {session.isSuccess &&
          (user ? (
            <p>
              Signed in as {user.name}.{' '}
              <Link to="/orders">Go to your orders</Link>
            </p>
          ) : (
            <SignInButton next={next} />
          ))}
        {session.isError && <SignInButton next={next} />}
      </main>
      <footer>
        <Link to="/privacy">Privacy policy</Link>
        <HealthStatus />
      </footer>
    </>
  );
}

export default Home;
