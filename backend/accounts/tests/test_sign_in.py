"""Signing in with Google, from the sign-in button to the signed-in session.

Google is faked (fake_google): its token endpoint returns an ID token signed with a test
key, which its fake key set publishes.
"""

import logging
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from django.test import Client
from responses import matchers

from accounts.models import User
from accounts.views import FLOWS_SESSION_KEY, MAX_FLOWS
from config.tests.test_proxy import DOMAIN, FROM_CLOUDFRONT
from integrations.google import TOKEN_ENDPOINT, pkce_challenge
from integrations.tests import fake_google
from integrations.tests.fake_google import ACCESS_TOKEN, CONFIG, SUB

from .factories import GoogleCredentialFactory

LOGIN_URL = "/api/auth/google/login/"
CALLBACK_URL = "/api/auth/google/callback/"
CODE = "4/0Atest-authorization-code"

pytestmark = pytest.mark.django_db


def query(url: str) -> dict[str, str]:
    return {name: values[0] for name, values in parse_qs(urlsplit(url).query).items()}


def start(client: Client, next_path: str | None = None, **headers: str) -> dict[str, str]:
    """Click the sign-in button, and return the parameters of Google's URL."""
    response = client.get(LOGIN_URL, {"next": next_path} if next_path else {}, headers=headers)
    assert response.status_code == 302
    assert response["Location"].startswith("https://accounts.google.com/")
    return query(response["Location"])


def fake_google_sign_in(google, flow: dict[str, str], **claims) -> None:
    """Google's side of a sign-in: its key set, and a token endpoint that returns an ID
    token for this flow's nonce. Claims override the ID token's."""
    fake_google.add_jwks(google)
    token = fake_google.id_token(**{"nonce": flow["nonce"], **claims})
    fake_google.add_token(google, id_token=token)


def callback(client: Client, **params: str):
    """Google's redirect back to the app."""
    return client.get(CALLBACK_URL, params)


def sign_in(client: Client, google, next_path: str | None = None, **claims):
    """A whole sign-in, returning the callback's response."""
    flow = start(client, next_path)
    fake_google_sign_in(google, flow, **claims)
    return callback(client, code=CODE, state=flow["state"])


def signed_in_user(client: Client) -> User | None:
    user_id = client.session.get("_auth_user_id")
    return User.objects.get(pk=user_id) if user_id else None


# Starting


def test_start_redirects_to_google_with_a_new_flow(client):
    params = start(client)

    assert params["client_id"] == CONFIG.client_id
    assert params["redirect_uri"] == "http://testserver/api/auth/google/callback/"
    assert params["scope"] == "openid email profile"
    assert params["code_challenge_method"] == "S256"
    flow = client.session[FLOWS_SESSION_KEY][params["state"]]
    assert flow["nonce"] == params["nonce"]
    assert pkce_challenge(flow["verifier"]) == params["code_challenge"]
    assert flow["next"] == "/orders"


def test_start_answers_503_when_google_is_not_configured(client, settings):
    settings.GOOGLE_OAUTH_CLIENT_SECRET = ""

    response = client.get(LOGIN_URL)

    assert response.status_code == 503
    assert response.content == b"Google sign-in isn't configured."


def test_start_is_never_cached(client):
    response = client.get(LOGIN_URL)

    assert "no-store" in response["Cache-Control"]


def test_redirect_url_behind_cloudfront_uses_https_and_the_domain(client, settings):
    settings.ALLOWED_HOSTS = [DOMAIN]
    settings.SECURE_PROXY_SSL_HEADER = ("HTTP_CLOUDFRONT_FORWARDED_PROTO", "https")

    params = start(client, **FROM_CLOUDFRONT)

    assert params["redirect_uri"] == f"https://{DOMAIN}/api/auth/google/callback/"


def test_flows_in_two_tabs_both_finish(client, google):
    first = start(client)
    second = start(client)
    fake_google_sign_in(google, second)

    assert callback(client, code=CODE, state=second["state"])["Location"] == "/orders"
    assert first["state"] in client.session[FLOWS_SESSION_KEY]


def test_only_the_newest_flows_are_kept(client):
    states = [start(client)["state"] for _ in range(MAX_FLOWS + 2)]

    assert list(client.session[FLOWS_SESSION_KEY]) == states[-MAX_FLOWS:]


# Signing in


def test_first_sign_in_creates_the_user(client, google):
    response = sign_in(client, google)

    assert response.status_code == 302
    assert response["Location"] == "/orders"
    user = signed_in_user(client)
    assert user is not None
    assert user.username == f"google-{SUB}"
    assert not user.has_usable_password()
    assert (user.email, user.first_name, user.last_name) == (
        "ada@example.com",
        "Ada",
        "Lovelace",
    )
    assert user.google_credential.google_sub == SUB


def test_returning_user_is_found_by_sub_after_an_email_change(client, google):
    credential = GoogleCredentialFactory(google_sub=SUB, user__email="old@example.com")

    sign_in(client, google, email="new@example.com", given_name="Augusta")

    user = signed_in_user(client)
    assert user == credential.user
    assert (user.email, user.first_name) == ("new@example.com", "Augusta")
    assert User.objects.count() == 1


def test_a_new_account_with_a_known_email_is_a_new_user(client, google):
    # Email addresses can move between Google accounts; the account ID can't.
    GoogleCredentialFactory(user__email="ada@example.com")

    sign_in(client, google)

    assert signed_in_user(client).google_credential.google_sub == SUB
    assert User.objects.count() == 2


def test_sign_in_goes_to_next(client, google):
    response = sign_in(client, google, next_path="/settings?tab=drive")

    assert response["Location"] == "/settings?tab=drive"


@pytest.mark.parametrize(
    "next_path",
    ["//evil.example", "https://evil.example/", "/\\evil.example", "orders", "javascript:x"],
)
def test_next_outside_the_app_falls_back_to_orders(client, google, next_path):
    response = sign_in(client, google, next_path=next_path)

    assert response["Location"] == "/orders"


def test_session_id_changes_at_sign_in(client, google):
    flow = start(client)
    before = client.cookies["sessionid"].value
    fake_google_sign_in(google, flow)

    callback(client, code=CODE, state=flow["state"])

    assert client.cookies["sessionid"].value != before
    assert signed_in_user(client) is not None


def test_exchange_sends_the_flows_verifier_to_this_redirect_url(client, google):
    flow = start(client)
    verifier = client.session[FLOWS_SESSION_KEY][flow["state"]]["verifier"]
    fake_google.add_jwks(google)
    google.post(
        TOKEN_ENDPOINT,
        json=fake_google.token_response(id_token=fake_google.id_token(nonce=flow["nonce"])),
        match=[
            matchers.urlencoded_params_matcher(
                {
                    "grant_type": "authorization_code",
                    "code": CODE,
                    "redirect_uri": flow["redirect_uri"],
                    "code_verifier": verifier,
                    "client_id": CONFIG.client_id,
                    "client_secret": CONFIG.client_secret,
                }
            )
        ],
    )

    assert callback(client, code=CODE, state=flow["state"])["Location"] == "/orders"


def test_inactive_user_is_refused(client, google):
    GoogleCredentialFactory(google_sub=SUB, user__is_active=False)

    response = sign_in(client, google)

    assert response["Location"] == "/?signin=failed"
    assert signed_in_user(client) is None


# Failures


def failed(response) -> bool:
    return response.status_code == 302 and response["Location"] == "/?signin=failed"


def test_cancelling_at_google_returns_cancelled(client):
    flow = start(client)

    response = callback(client, error="access_denied", state=flow["state"])

    assert response["Location"] == "/?signin=cancelled"
    assert flow["state"] not in client.session[FLOWS_SESSION_KEY]


def test_another_error_from_google_fails(client, caplog):
    flow = start(client)

    response = callback(client, error="server_error", state=flow["state"])

    assert failed(response)
    assert "google_error:server_error" in caplog.text


def test_missing_state_fails(client, google):
    flow = start(client)
    fake_google_sign_in(google, flow)

    assert failed(callback(client, code=CODE))
    assert signed_in_user(client) is None


def test_forged_callback_with_another_state_fails(client, google, caplog):
    # An attacker's own code and state, sent to the victim's browser.
    flow = start(client)
    fake_google_sign_in(google, flow)

    assert failed(callback(client, code=CODE, state="attackers-state"))
    assert signed_in_user(client) is None
    assert "unknown_state" in caplog.text


def test_callback_from_another_browser_fails(client, google):
    flow = start(client)
    fake_google_sign_in(google, flow)

    assert failed(callback(Client(), code=CODE, state=flow["state"]))


def test_expired_flow_fails(client, google, caplog):
    flow = start(client)
    fake_google_sign_in(google, flow)
    session = client.session
    session[FLOWS_SESSION_KEY][flow["state"]]["started"] = time.time() - 601
    session.save()

    assert failed(callback(client, code=CODE, state=flow["state"]))
    assert "flow_expired" in caplog.text


def test_reused_state_fails(client, google):
    flow = start(client)
    fake_google_sign_in(google, flow)
    assert callback(client, code=CODE, state=flow["state"])["Location"] == "/orders"

    assert failed(callback(client, code=CODE, state=flow["state"]))


def test_replayed_id_token_with_another_nonce_fails(client, google, caplog):
    # An ID token issued for an earlier sign-in carries that sign-in's nonce.
    flow = start(client)
    fake_google_sign_in(google, flow, nonce="an-earlier-nonce")

    assert failed(callback(client, code=CODE, state=flow["state"]))
    assert signed_in_user(client) is None
    assert "nonce doesn't match" in caplog.text


def test_id_token_for_another_client_fails(client, google, caplog):
    flow = start(client)
    fake_google_sign_in(google, flow, aud="another-client.apps.googleusercontent.com")

    assert failed(callback(client, code=CODE, state=flow["state"]))
    assert "InvalidAudienceError" in caplog.text


def test_missing_code_fails(client):
    flow = start(client)

    assert failed(callback(client, state=flow["state"]))


def test_used_code_fails(client, google, caplog):
    flow = start(client)
    fake_google.add_token_error(google, "invalid_grant")

    assert failed(callback(client, code=CODE, state=flow["state"]))
    assert "InvalidGrant" in caplog.text


def test_google_unavailable_fails(client, google, caplog):
    flow = start(client)
    google.post(TOKEN_ENDPOINT, status=503)

    assert failed(callback(client, code=CODE, state=flow["state"]))
    assert "GoogleUnavailable" in caplog.text


def test_an_error_parameter_is_not_logged_as_given(client, caplog):
    callback(client, error="x\nFAKE LOG LINE")

    assert "FAKE LOG LINE" not in caplog.text
    assert "google_error:other" in caplog.text


# Logs


def test_logs_hold_no_code_state_token_or_email(client, google, caplog):
    caplog.set_level(logging.DEBUG)
    flow = start(client)
    fake_google_sign_in(google, flow)
    callback(client, code=CODE, state=flow["state"])
    callback(client, code=CODE, state=flow["state"])  # A replay, which fails.

    user = User.objects.get()
    assert f"Google sign-in: user {user.pk} (new user)" in caplog.text
    assert "unknown_state" in caplog.text
    for secret in [CODE, flow["state"], flow["nonce"], ACCESS_TOKEN, "ada@example.com"]:
        assert secret not in caplog.text
