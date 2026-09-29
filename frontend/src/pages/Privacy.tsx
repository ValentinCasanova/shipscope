import { Link } from 'react-router';

// Update the date, and the text, whenever what ShipScope stores or shares
// changes: storing Sheet rows (6.1), sending orders to EasyPost (6.2) or to
// Anthropic (8.x).
const LAST_UPDATED = '2026-09-29';
const OPERATOR = 'Valentin Casanova';
const CONTACT_EMAIL = 'vkcnova@gmail.com';

/** The privacy policy, which Google's consent screen links to. */
function Privacy() {
  return (
    <main className="privacy">
      <h1>Privacy policy</h1>
      <p>Last updated {LAST_UPDATED}.</p>

      <h2>Who runs ShipScope</h2>
      <p>
        ShipScope is a project built and run by {OPERATOR}. Questions and
        requests go to <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
      </p>

      <h2>What ShipScope stores</h2>
      <ul>
        <li>
          <strong>
            Your Google account&apos;s ID, name, and email address
          </strong>
          , when you sign in with Google. ShipScope uses them to recognize you
          and to show who is signed in. It never sees your Google password.
        </li>
        <li>
          <strong>Access to Google Drive, only if you connect it.</strong>{' '}
          ShipScope then asks for access to only the files you open with it, not
          your whole Drive. It stores the access Google grants, encrypted, so it
          can read the Sheet you picked.
        </li>
        <li>
          <strong>Your orders</strong>, once you connect a Sheet: the rows of
          the Sheet you picked, the shipping rates quoted for them, and any
          flags ShipScope raised about them.
        </li>
        <li>
          <strong>Technical logs</strong>: each request&apos;s time, page, and
          browser, your account&apos;s number when you sign in or out, and error
          details, to keep the service running. They don&apos;t contain your
          email address, your Google data, or access tokens.
        </li>
      </ul>
      <p>
        ShipScope sets one cookie to keep you signed in, and one that protects
        your requests against forgery. It uses no tracking or advertising
        cookies.
      </p>

      <h2>Where it&apos;s stored, and for how long</h2>
      <p>
        Everything is stored on Amazon Web Services in the United States (Ohio).
        Your account and orders are kept until you ask for them to be deleted.
        Deleted data leaves the database backups within 7 days, and the logs
        within 30 days.
      </p>

      <h2>Who it&apos;s shared with</h2>
      <p>
        Nobody. ShipScope doesn&apos;t sell your data or share it with anyone,
        apart from the services that run the app: Amazon Web Services, which
        hosts it, and Google, for signing in and reading your Sheet.
      </p>

      <h2>Google user data</h2>
      <p>
        ShipScope&apos;s use and transfer to any other app of information
        received from Google APIs will adhere to the{' '}
        <a href="https://developers.google.com/terms/api-services-user-data-policy">
          Google API Services User Data Policy
        </a>
        , including the Limited Use requirements. In particular, ShipScope uses
        your Google data only to provide the features you see in the app, never
        for advertising, and people read it only with your permission, for
        security, or when the law requires it.
      </p>

      <h2>Your choices</h2>
      <ul>
        <li>
          You can remove ShipScope&apos;s access to your Google account at any
          time, at{' '}
          <a href="https://myaccount.google.com/connections">
            myaccount.google.com/connections
          </a>
          . ShipScope then deletes the Drive access it stored the next time it
          tries to use it.
        </li>
        <li>
          To have your account and all its data deleted, email{' '}
          <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a> from the
          address you sign in with. It&apos;s done within 30 days.
        </li>
      </ul>

      <p>
        <Link to="/">Back to ShipScope</Link>
      </p>
    </main>
  );
}

export default Privacy;
