"""Google's OAuth 2.0 and OpenID Connect endpoints: signing in, and Drive access.

The flow runs on the server (the backend-for-frontend pattern): Django is the
confidential client, and no token ever reaches the browser. This module only talks to
Google. Where the flow's values are kept, and what happens to the user, is up to the
caller (accounts/services.py and accounts/views.py).

Every request has a timeout. The code exchange is never retried, because Google accepts
a code only once. Refreshing and revoking retry once after a connection error or a 5xx.

Nothing here logs or puts into an exception message a token, a code, or a PKCE
verifier. The dataclasses that hold them leave them out of their repr.
"""

import base64
import hashlib
import hmac
import logging
import secrets
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import jwt
import requests

logger = logging.getLogger(__name__)

AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"  # noqa: S105 (a URL)
REVOCATION_ENDPOINT = "https://oauth2.googleapis.com/revoke"
JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"
# Google's ID tokens carry either form.
ISSUERS = ("https://accounts.google.com", "accounts.google.com")

# Signing in asks only for the account's ID, name, and email (D16).
SIGN_IN_SCOPES = ("openid", "email", "profile")
# Only the files a user opens with ShipScope, asked for when they connect Drive (D16).
DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"

# Seconds to connect and to read. Together they stay under the 30 seconds Gunicorn and
# CloudFront allow a request, even with one retry of a connection error.
TIMEOUT = (3, 10)
# Allowed clock difference with Google when checking the ID token's times.
CLOCK_SKEW_SECONDS = 60
# Google rotates its signing keys every few weeks and publishes the next key well
# before using it, so an hour's cache is safe. An unknown key ID fetches them again.
JWKS_CACHE_SECONDS = 3600


class GoogleOAuthError(Exception):
    """Google refused a request, or answered with something unexpected."""


class GoogleUnavailable(GoogleOAuthError):
    """Google couldn't be reached in time, or answered with a server error."""


class InvalidGrant(GoogleOAuthError):
    """The code or refresh token is invalid: expired, already used, or revoked."""


class InvalidIdToken(GoogleOAuthError):
    """The ID token failed a check: signature, issuer, audience, expiry, or nonce."""


@dataclass(frozen=True)
class GoogleOAuthConfig:
    """One OAuth client from Google's console. Each environment has its own."""

    client_id: str
    client_secret: str = field(repr=False)

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)


@dataclass(frozen=True)
class PkcePair:
    """A PKCE verifier, kept by the server, and its S256 challenge, sent to Google."""

    verifier: str = field(repr=False)
    challenge: str


@dataclass(frozen=True)
class TokenResponse:
    """What Google's token endpoint returned for a code exchange or a refresh."""

    access_token: str = field(repr=False)
    expires_in: int
    # The scopes Google actually granted. Users can untick some on the consent screen.
    scopes: frozenset[str]
    # Only when the request included openid: always for a code exchange.
    id_token: str = field(default="", repr=False)
    # Only for a code exchange with access_type=offline after a consent screen.
    refresh_token: str = field(default="", repr=False)


@dataclass(frozen=True)
class GoogleIdentity:
    """The checked claims of an ID token that ShipScope uses."""

    # The account's ID. It never changes, unlike the email address.
    sub: str
    email: str
    email_verified: bool
    # Both can be blank: Google leaves out what the account doesn't have.
    given_name: str
    family_name: str


def new_state() -> str:
    """A random value that ties Google's redirect back to the flow that started it."""
    return secrets.token_urlsafe(32)


def new_nonce() -> str:
    """A random value that Google copies into the ID token, tying it to this flow."""
    return secrets.token_urlsafe(32)


def new_pkce_pair() -> PkcePair:
    """A PKCE verifier and its S256 challenge (RFC 7636).

    64 random bytes give an 86-character verifier; the RFC allows 43 to 128.
    """
    verifier = secrets.token_urlsafe(64)
    return PkcePair(verifier=verifier, challenge=pkce_challenge(verifier))


def pkce_challenge(verifier: str) -> str:
    """The S256 challenge: the verifier's SHA-256 hash, base64url-encoded without padding."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


class _GoogleKeys(jwt.PyJWKClient):
    """Google's published signing keys, fetched with the client's session and timeout.

    PyJWKClient caches the keys, and fetches them again when a token names an unknown
    key ID. Only the fetch is replaced: PyJWKClient uses urllib, without the session's
    timeout, and tests fake Google's endpoints at the session.
    """

    def __init__(self, session: requests.Session) -> None:
        super().__init__(JWKS_URI, lifespan=JWKS_CACHE_SECONDS)
        self._session = session

    def fetch_data(self) -> Any:
        try:
            response = self._session.get(self.uri, timeout=TIMEOUT)
        except requests.RequestException as error:
            raise GoogleUnavailable(
                f"Fetching Google's keys failed: {type(error).__name__}"
            ) from error
        if response.status_code != 200:
            raise GoogleUnavailable(
                f"Fetching Google's keys failed with HTTP {response.status_code}"
            )
        return response.json()


class GoogleOAuthClient:
    """Google's authorization, token, and revocation endpoints, for one OAuth client."""

    def __init__(self, config: GoogleOAuthConfig, session: requests.Session | None = None) -> None:
        self._config = config
        self._session = session or requests.Session()
        self._keys = _GoogleKeys(self._session)

    def authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        nonce: str,
        code_challenge: str,
        scopes: Iterable[str] = SIGN_IN_SCOPES,
        offline: bool = False,
        prompt: str | None = None,
        login_hint: str | None = None,
        include_granted_scopes: bool = False,
    ) -> str:
        """The URL of Google's sign-in and consent screen, to redirect the browser to.

        offline asks for a refresh token, which Google returns only after a consent
        screen, so pair it with prompt="consent". login_hint preselects an account, by
        email or by sub.
        """
        params = {
            "response_type": "code",
            "client_id": self._config.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scopes),
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if offline:
            params["access_type"] = "offline"
        if prompt:
            params["prompt"] = prompt
        if login_hint:
            params["login_hint"] = login_hint
        if include_granted_scopes:
            params["include_granted_scopes"] = "true"
        return f"{AUTHORIZATION_ENDPOINT}?{urlencode(params)}"

    def exchange_code(self, *, code: str, redirect_uri: str, code_verifier: str) -> TokenResponse:
        """Exchange the code from Google's redirect for tokens. Never retried."""
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
            **self._client_credentials(),
        }
        return _token_response(self._post(TOKEN_ENDPOINT, data, retry=False))

    def refresh(self, refresh_token: str) -> TokenResponse:
        """A new access token for a refresh token. InvalidGrant if it was revoked."""
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            **self._client_credentials(),
        }
        return _token_response(self._post(TOKEN_ENDPOINT, data, retry=True))

    def revoke(self, token: str) -> None:
        """Revoke a refresh token, or an access token, and the grant behind it.

        A token that's already invalid counts as revoked.
        """
        try:
            self._post(REVOCATION_ENDPOINT, {"token": token}, retry=True)
        except GoogleOAuthError as error:
            # Google answers invalid_token for a token that expired or was revoked.
            if str(error) != "invalid_token":
                raise

    def verify_id_token(self, id_token: str, *, nonce: str) -> GoogleIdentity:
        """Check an ID token in full, and return its claims.

        Checks the signature against Google's published keys, the issuer, that the
        audience is this client, the expiry, and that the nonce is this flow's.
        OpenID Connect allows skipping the signature for a token fetched straight from
        Google over TLS, but checking it costs only a cached key lookup.
        """
        try:
            signing_key = self._keys.get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self._config.client_id,
                issuer=ISSUERS,
                leeway=CLOCK_SKEW_SECONDS,
                options={"require": ["iss", "aud", "sub", "exp", "iat", "nonce"]},
            )
        except (jwt.PyJWTError, jwt.PyJWKClientError) as error:
            # PyJWT's messages name the failed check, never the token.
            raise InvalidIdToken(f"{type(error).__name__}: {error}") from error
        if not hmac.compare_digest(str(claims["nonce"]), nonce):
            raise InvalidIdToken("The nonce doesn't match this sign-in")
        given_name = str(claims.get("given_name", ""))
        family_name = str(claims.get("family_name", ""))
        if not (given_name or family_name):
            # A name that doesn't split into the two parts.
            given_name = str(claims.get("name", ""))
        return GoogleIdentity(
            sub=str(claims["sub"]),
            email=str(claims.get("email", "")),
            email_verified=claims.get("email_verified") is True,
            given_name=given_name,
            family_name=family_name,
        )

    def _client_credentials(self) -> dict[str, str]:
        return {"client_id": self._config.client_id, "client_secret": self._config.client_secret}

    def _post(self, url: str, data: dict[str, str], *, retry: bool) -> dict[str, Any]:
        """POST a form to Google and return the JSON body of a 200.

        Raises InvalidGrant for invalid_grant, GoogleUnavailable for timeouts,
        connection errors, and 5xx, and GoogleOAuthError, with Google's error code as
        its message, for any other refusal.
        """
        attempts = 2 if retry else 1
        for attempt in range(1, attempts + 1):
            try:
                response = self._session.post(url, data=data, timeout=TIMEOUT)
            except requests.ConnectionError as error:
                # Includes a connect timeout: the request never reached Google.
                failure = f"{type(error).__name__} from {url}"
                if _retrying(attempt, attempts, failure):
                    continue
                raise GoogleUnavailable(failure) from error
            except requests.RequestException as error:
                # A read timeout: Google may have processed the request.
                raise GoogleUnavailable(f"{type(error).__name__} from {url}") from error
            if response.status_code >= 500:
                failure = f"HTTP {response.status_code} from {url}"
                if _retrying(attempt, attempts, failure):
                    continue
                raise GoogleUnavailable(failure)
            return _json_or_error(response)
        raise AssertionError("unreachable")  # pragma: no cover


def _retrying(attempt: int, attempts: int, failure: str) -> bool:
    if attempt < attempts:
        logger.warning("Google request failed, retrying once: %s", failure)
        return True
    return False


def _json_or_error(response: requests.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except requests.JSONDecodeError:
        body = None
    if response.status_code == 200:
        # The revocation endpoint answers 200 with an empty body.
        return body if isinstance(body, dict) else {}
    error = body.get("error") if isinstance(body, dict) else None
    if error == "invalid_grant":
        raise InvalidGrant("invalid_grant")
    raise GoogleOAuthError(error if isinstance(error, str) else f"HTTP {response.status_code}")


def _token_response(body: dict[str, Any]) -> TokenResponse:
    if not isinstance(body.get("access_token"), str) or not body["access_token"]:
        raise GoogleOAuthError("The token response has no access_token")
    if not isinstance(body.get("expires_in"), int):
        raise GoogleOAuthError("The token response has no expires_in")
    return TokenResponse(
        access_token=body["access_token"],
        expires_in=body["expires_in"],
        scopes=frozenset(str(body.get("scope", "")).split()),
        id_token=str(body.get("id_token", "")),
        refresh_token=str(body.get("refresh_token", "")),
    )
