import { Link } from 'react-router';

function NotFound() {
  return (
    <main>
      <h1>Page not found</h1>
      <p>
        There&apos;s no page at this address.{' '}
        <Link to="/">Go to ShipScope</Link>
      </p>
    </main>
  );
}

export default NotFound;
