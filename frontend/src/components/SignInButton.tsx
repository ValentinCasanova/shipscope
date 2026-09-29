import { signInUrl } from '../api/session.ts';
import buttonImage from '../assets/google-sign-in.svg';

/**
 * Google's "Sign in with Google" button, light theme, from Google's branding
 * assets, unchanged as their guidelines require. A plain link: signing in
 * leaves the app for Google's own screen.
 */
function SignInButton({ next }: { next?: string | null }) {
  return (
    <a href={signInUrl(next)} className="sign-in-button">
      <img
        src={buttonImage}
        alt="Sign in with Google"
        width={180}
        height={40}
      />
    </a>
  );
}

export default SignInButton;
