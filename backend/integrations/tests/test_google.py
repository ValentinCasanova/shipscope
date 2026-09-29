import logging
import re
import time
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
import responses
from responses import matchers

from integrations.google import (
    DRIVE_FILE_SCOPE,
    REVOCATION_ENDPOINT,
    TIMEOUT,
    TOKEN_ENDPOINT,
    GoogleOAuthClient,
    GoogleOAuthConfig,
    GoogleOAuthError,
    GoogleUnavailable,
    InvalidGrant,
    InvalidIdToken,
    new_pkce_pair,
    pkce_challenge,
)

from . import fake_google
from .fake_google import ACCESS_TOKEN, CONFIG, NONCE, REFRESH_TOKEN, SUB

REDIRECT_URI = "https://staging.shipscope.net/api/auth/google/callback/"


@pytest.fixture
def google():
    """Fakes Google's endpoints. Any request to a URL no test added fails the test."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.fixture
def client():
    return GoogleOAuthClient(CONFIG)


def query(url: str) -> dict[str, str]:
    return {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}


# Configuration


def test_config_keeps_the_secret_out_of_its_repr():
    assert "test-client-secret" not in repr(CONFIG)


@pytest.mark.parametrize(
    ("client_id", "client_secret", "configured"),
    [("id", "secret", True), ("id", "", False), ("", "secret", False)],
)
def test_config_is_configured_with_both_values(client_id, client_secret, configured):
    assert GoogleOAuthConfig(client_id, client_secret).configured is configured


# PKCE


def test_pkce_challenge_matches_the_rfcs_example():
    # RFC 7636, appendix B.
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    assert pkce_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_pkce_pair_holds_a_valid_verifier_and_its_challenge():
    pair = new_pkce_pair()

    assert re.fullmatch(r"[A-Za-z0-9_-]{43,128}", pair.verifier)
    assert pair.challenge == pkce_challenge(pair.verifier)
    assert pair.verifier not in repr(pair)


def test_pkce_pairs_are_random():
    assert new_pkce_pair().verifier != new_pkce_pair().verifier


# The authorization URL


def test_authorization_url_for_signing_in(client):
    url = client.authorization_url(
        redirect_uri=REDIRECT_URI, state="the-state", nonce=NONCE, code_challenge="the-challenge"
    )

    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert query(url) == {
        "response_type": "code",
        "client_id": CONFIG.client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": "openid email profile",
        "state": "the-state",
        "nonce": NONCE,
        "code_challenge": "the-challenge",
        "code_challenge_method": "S256",
    }


def test_authorization_url_for_connecting_drive(client):
    url = client.authorization_url(
        redirect_uri=REDIRECT_URI,
        state="the-state",
        nonce=NONCE,
        code_challenge="the-challenge",
        scopes=["openid", "email", "profile", DRIVE_FILE_SCOPE],
        offline=True,
        prompt="consent",
        login_hint=SUB,
        include_granted_scopes=True,
    )

    params = query(url)
    assert params["scope"] == f"openid email profile {DRIVE_FILE_SCOPE}"
    assert params["access_type"] == "offline"
    assert params["prompt"] == "consent"
    assert params["login_hint"] == SUB
    assert params["include_granted_scopes"] == "true"


# The code exchange


def test_exchange_sends_the_code_verifier_and_secret(client, google):
    google.post(
        TOKEN_ENDPOINT,
        json=fake_google.token_response(),
        match=[
            matchers.urlencoded_params_matcher(
                {
                    "grant_type": "authorization_code",
                    "code": "the-code",
                    "redirect_uri": REDIRECT_URI,
                    "code_verifier": "the-verifier",
                    "client_id": CONFIG.client_id,
                    "client_secret": CONFIG.client_secret,
                }
            ),
            matchers.request_kwargs_matcher({"timeout": TIMEOUT}),
        ],
    )

    tokens = client.exchange_code(
        code="the-code", redirect_uri=REDIRECT_URI, code_verifier="the-verifier"
    )

    assert tokens.access_token == ACCESS_TOKEN
    assert tokens.expires_in == 3599
    assert "openid" in tokens.scopes
    assert tokens.id_token
    assert tokens.refresh_token == ""
    assert ACCESS_TOKEN not in repr(tokens)


def test_exchange_returns_the_refresh_token(client, google):
    fake_google.add_token(google, refresh_token=REFRESH_TOKEN)

    tokens = client.exchange_code(code="c", redirect_uri=REDIRECT_URI, code_verifier="v")

    assert tokens.refresh_token == REFRESH_TOKEN
    assert REFRESH_TOKEN not in repr(tokens)


def test_exchange_of_a_used_code_raises_invalid_grant(client, google):
    fake_google.add_token_error(google, "invalid_grant")

    with pytest.raises(InvalidGrant):
        client.exchange_code(code="c", redirect_uri=REDIRECT_URI, code_verifier="v")


def test_other_refusals_raise_googles_error_code(client, google):
    fake_google.add_token_error(google, "invalid_client", status=401)

    with pytest.raises(GoogleOAuthError, match=r"^invalid_client$") as raised:
        client.exchange_code(code="c", redirect_uri=REDIRECT_URI, code_verifier="v")
    assert type(raised.value) is GoogleOAuthError


def test_a_token_response_without_an_access_token_is_refused(client, google):
    fake_google.add_token(google, access_token=None)

    with pytest.raises(GoogleOAuthError, match="no access_token"):
        client.exchange_code(code="c", redirect_uri=REDIRECT_URI, code_verifier="v")


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(requests.ConnectTimeout(), id="connect-timeout"),
        pytest.param(requests.ReadTimeout(), id="read-timeout"),
        pytest.param(requests.ConnectionError(), id="connection-error"),
    ],
)
def test_exchange_is_never_retried(client, google, failure):
    call = google.post(TOKEN_ENDPOINT, body=failure)

    with pytest.raises(GoogleUnavailable):
        client.exchange_code(code="c", redirect_uri=REDIRECT_URI, code_verifier="v")
    assert call.call_count == 1


def test_exchange_is_not_retried_after_a_server_error(client, google):
    call = google.post(TOKEN_ENDPOINT, status=503)

    with pytest.raises(GoogleUnavailable, match="HTTP 503"):
        client.exchange_code(code="c", redirect_uri=REDIRECT_URI, code_verifier="v")
    assert call.call_count == 1


# Refreshing and revoking


def test_refresh_returns_a_new_access_token(client, google):
    google.post(
        TOKEN_ENDPOINT,
        json=fake_google.token_response(id_token=None, scope=DRIVE_FILE_SCOPE),
        match=[
            matchers.urlencoded_params_matcher(
                {
                    "grant_type": "refresh_token",
                    "refresh_token": REFRESH_TOKEN,
                    "client_id": CONFIG.client_id,
                    "client_secret": CONFIG.client_secret,
                }
            )
        ],
    )

    tokens = client.refresh(REFRESH_TOKEN)

    assert tokens.access_token == ACCESS_TOKEN
    assert tokens.scopes == {DRIVE_FILE_SCOPE}


def test_refresh_of_a_revoked_token_raises_invalid_grant(client, google):
    fake_google.add_token_error(google, "invalid_grant")

    with pytest.raises(InvalidGrant):
        client.refresh(REFRESH_TOKEN)


@pytest.mark.parametrize(
    "first",
    [
        pytest.param({"status": 503}, id="server-error"),
        pytest.param({"body": requests.ConnectionError()}, id="connection-error"),
    ],
)
def test_refresh_retries_once(client, google, first, caplog):
    google.post(TOKEN_ENDPOINT, **first)
    google.post(TOKEN_ENDPOINT, json=fake_google.token_response())

    assert client.refresh(REFRESH_TOKEN).access_token == ACCESS_TOKEN
    assert "retrying once" in caplog.text


def test_refresh_gives_up_after_the_second_server_error(client, google):
    call = google.post(TOKEN_ENDPOINT, status=500)

    with pytest.raises(GoogleUnavailable):
        client.refresh(REFRESH_TOKEN)
    assert call.call_count == 2


def test_refresh_is_not_retried_after_a_read_timeout(client, google):
    # Google may have issued a token already; the caller decides what to do.
    call = google.post(TOKEN_ENDPOINT, body=requests.ReadTimeout())

    with pytest.raises(GoogleUnavailable):
        client.refresh(REFRESH_TOKEN)
    assert call.call_count == 1


def test_revoke_posts_the_token(client, google):
    call = google.post(
        REVOCATION_ENDPOINT, match=[matchers.urlencoded_params_matcher({"token": REFRESH_TOKEN})]
    )

    client.revoke(REFRESH_TOKEN)

    assert call.call_count == 1


def test_revoking_an_invalid_token_counts_as_revoked(client, google):
    google.post(REVOCATION_ENDPOINT, json={"error": "invalid_token"}, status=400)

    client.revoke(REFRESH_TOKEN)


def test_revoke_retries_once(client, google):
    google.post(REVOCATION_ENDPOINT, status=502)
    google.post(REVOCATION_ENDPOINT)

    client.revoke(REFRESH_TOKEN)


# The ID token


@pytest.fixture
def keys(google):
    fake_google.add_jwks(google)
    return google


def test_valid_id_token_returns_the_identity(client, keys):
    identity = client.verify_id_token(fake_google.id_token(), nonce=NONCE)

    assert identity.sub == SUB
    assert identity.email == "ada@example.com"
    assert identity.email_verified is True
    assert identity.name == "Ada Lovelace"


def test_either_issuer_form_is_accepted(client, keys):
    token = fake_google.id_token(iss="accounts.google.com")

    assert client.verify_id_token(token, nonce=NONCE).sub == SUB


@pytest.mark.parametrize(
    ("token", "reason"),
    [
        pytest.param(
            lambda: fake_google.id_token(key=fake_google.signing_key("attacker")),
            "InvalidSignatureError",
            id="wrong-signature",
        ),
        pytest.param(
            lambda: fake_google.id_token(aud="another-client.apps.googleusercontent.com"),
            "InvalidAudienceError",
            id="wrong-audience",
        ),
        pytest.param(
            lambda: fake_google.id_token(iss="https://accounts.example.com"),
            "InvalidIssuerError",
            id="wrong-issuer",
        ),
        pytest.param(
            lambda: fake_google.id_token(iat=int(time.time()) - 7200, exp=int(time.time()) - 3600),
            "ExpiredSignatureError",
            id="expired",
        ),
        pytest.param(
            lambda: fake_google.id_token(nonce="another-nonce"),
            "nonce doesn't match",
            id="wrong-nonce",
        ),
        pytest.param(
            lambda: fake_google.id_token(nonce=None),
            "MissingRequiredClaimError",
            id="no-nonce",
        ),
        pytest.param(
            lambda: fake_google.id_token(kid="unknown-key"),
            "Unable to find a signing key",
            id="unknown-key-id",
        ),
    ],
)
def test_id_token_is_refused(client, keys, token, reason):
    with pytest.raises(InvalidIdToken, match=reason):
        client.verify_id_token(token(), nonce=NONCE)


def test_keys_are_cached(client, google):
    call = google.get(fake_google.JWKS_URI, json=fake_google.jwks())

    client.verify_id_token(fake_google.id_token(), nonce=NONCE)
    client.verify_id_token(fake_google.id_token(), nonce=NONCE)

    assert call.call_count == 1


def test_an_unknown_key_id_fetches_the_keys_again(client, google):
    # Google started signing with a key published after the cached set.
    google.get(fake_google.JWKS_URI, json=fake_google.jwks(kid="old-key"))
    google.get(fake_google.JWKS_URI, json=fake_google.jwks(kid="new-key"))

    token = fake_google.id_token(kid="new-key")

    assert client.verify_id_token(token, nonce=NONCE).sub == SUB


def test_unreachable_keys_raise_google_unavailable(client, google):
    google.get(fake_google.JWKS_URI, body=requests.ConnectTimeout())

    with pytest.raises(GoogleUnavailable):
        client.verify_id_token(fake_google.id_token(), nonce=NONCE)


# Logs


def test_nothing_logged_contains_a_token(client, google, caplog):
    caplog.set_level(logging.DEBUG)
    google.post(TOKEN_ENDPOINT, status=503)
    google.post(TOKEN_ENDPOINT, json=fake_google.token_response(refresh_token=REFRESH_TOKEN))
    fake_google.add_jwks(google)

    tokens = client.refresh(REFRESH_TOKEN)
    client.verify_id_token(tokens.id_token, nonce=NONCE)
    with pytest.raises(InvalidIdToken) as refused:
        client.verify_id_token(tokens.id_token, nonce="another-nonce")

    logged = caplog.text + str(refused.value)
    assert "retrying once" in logged
    for secret in [ACCESS_TOKEN, REFRESH_TOKEN, tokens.id_token, CONFIG.client_secret]:
        assert secret not in logged
