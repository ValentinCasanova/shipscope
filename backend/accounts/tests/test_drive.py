"""Connecting Google Drive, keeping its access token fresh, and disconnecting it.

Google is faked (fake_google), as in test_sign_in.py. The signed-in user signs in with
the fake Google account (SUB), whose ID tokens the fake token endpoint returns.
"""

import json
import logging
from datetime import timedelta

import pytest
import responses
from django.test import Client
from django.utils import timezone
from responses import matchers

from accounts.models import GoogleCredential
from accounts.services import (
    DRIVE_DISCONNECTED,
    DriveAccessRevoked,
    DriveNotConnected,
    drive_access_token,
)
from accounts.views import FLOWS_SESSION_KEY
from integrations.google import (
    DRIVE_FILE_SCOPE,
    REVOCATION_ENDPOINT,
    TOKEN_ENDPOINT,
    GoogleUnavailable,
)
from integrations.tests import fake_google
from integrations.tests.fake_google import (
    ACCESS_TOKEN,
    CONFIG,
    DRIVE_SCOPES,
    REFRESH_TOKEN,
    SUB,
)

from .factories import GoogleCredentialFactory, UserFactory
from .test_fields import stored_tokens
from .test_sign_in import callback, query, sign_in

CONNECT_URL = "/api/auth/google/drive/connect/"
DRIVE_URL = "/api/auth/google/drive/"
CODE = "4/0Atest-drive-authorization-code"
NEW_ACCESS_TOKEN = "ya29.test-new-access-token"
BASIC_SCOPES = (
    "openid https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile"
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def credential():
    """The signed-in user's Google account, without Drive."""
    return GoogleCredentialFactory(google_sub=SUB)


@pytest.fixture
def signed_in(client, credential):
    client.force_login(credential.user)
    return client


def start_connecting(client: Client, next_path: str | None = None) -> dict[str, str]:
    """Click "Connect Google Drive", and return the parameters of Google's URL."""
    response = client.get(CONNECT_URL, {"next": next_path} if next_path else {})
    assert response.status_code == 302
    assert response["Location"].startswith("https://accounts.google.com/")
    return query(response["Location"])


def fake_google_consent(google, flow: dict[str, str], *, sub: str = SUB, **fields) -> None:
    """Google's side of connecting Drive: the account's ID token for this flow, a refresh
    token, and drive.file among the granted scopes. fields override the token response's."""
    fake_google.add_jwks(google)
    token = fake_google.id_token(nonce=flow["nonce"], sub=sub)
    defaults = {"id_token": token, "refresh_token": REFRESH_TOKEN, "scope": DRIVE_SCOPES}
    fake_google.add_token(google, **{**defaults, **fields})


def connect(client: Client, google, next_path: str | None = None, **consent):
    """A whole connection, returning the callback's response."""
    flow = start_connecting(client, next_path)
    fake_google_consent(google, flow, **consent)
    return callback(client, code=CODE, state=flow["state"])


def assert_not_connected(credential: GoogleCredential) -> None:
    credential.refresh_from_db()
    assert {name: getattr(credential, name) for name in DRIVE_DISCONNECTED} == DRIVE_DISCONNECTED
    assert stored_tokens(credential) == ("", "")


# Starting


def test_start_asks_for_drive_file_with_offline_access_and_consent(signed_in, credential):
    params = start_connecting(signed_in)

    assert params["client_id"] == CONFIG.client_id
    assert params["scope"] == f"openid email profile {DRIVE_FILE_SCOPE}"
    assert params["access_type"] == "offline"
    assert params["prompt"] == "consent"
    assert params["include_granted_scopes"] == "true"
    assert params["login_hint"] == SUB
    assert params["code_challenge_method"] == "S256"
    flow = signed_in.session[FLOWS_SESSION_KEY][params["state"]]
    assert flow["purpose"] == "connect_drive"
    assert flow["user_id"] == credential.user.pk
    assert flow["next"] == "/settings"


def test_start_sends_signed_out_visitors_home(client):
    response = client.get(CONNECT_URL)

    assert response.status_code == 302
    assert response["Location"] == "/?next=%2Fsettings"


@pytest.mark.parametrize("setting", ["GOOGLE_OAUTH_CLIENT_SECRET", "TOKEN_ENCRYPTION_KEY"])
def test_start_answers_503_when_not_configured(signed_in, settings, setting):
    setattr(settings, setting, "")

    response = signed_in.get(CONNECT_URL)

    assert response.status_code == 503
    assert response.content == b"Connecting Google Drive isn't configured."


def test_a_user_who_doesnt_sign_in_with_google_cant_connect(client):
    # Such as the admin, signed in with a password.
    client.force_login(UserFactory())

    response = client.get(CONNECT_URL)

    assert response["Location"] == "/settings?drive=failed"
    assert FLOWS_SESSION_KEY not in client.session


def test_start_is_never_cached(signed_in):
    assert "no-store" in signed_in.get(CONNECT_URL)["Cache-Control"]


# Connecting


def test_connecting_stores_the_tokens_encrypted(signed_in, credential, google):
    before = timezone.now()

    response = connect(signed_in, google)

    assert response.status_code == 302
    assert response["Location"] == "/settings?drive=connected"
    refresh_token, access_token = stored_tokens(credential)
    assert refresh_token.startswith("gAAAAA")
    assert access_token.startswith("gAAAAA")
    credential.refresh_from_db()
    assert (credential.refresh_token, credential.access_token) == (REFRESH_TOKEN, ACCESS_TOKEN)
    assert DRIVE_FILE_SCOPE in credential.granted_scopes.split()
    assert before <= credential.drive_connected_at <= timezone.now()
    expected_expiry = credential.drive_connected_at + timedelta(seconds=3599)
    assert credential.access_token_expires_at == expected_expiry
    assert signed_in.get("/api/auth/session/").json()["user"]["google_drive_connected"]


def test_connecting_goes_back_to_next_with_the_result(signed_in, google):
    response = connect(signed_in, google, next_path="/settings?tab=drive")

    assert response["Location"] == "/settings?tab=drive&drive=connected"


def test_next_outside_the_app_falls_back_to_settings(signed_in, google):
    response = connect(signed_in, google, next_path="//evil.example")

    assert response["Location"] == "/settings?drive=connected"


def test_connecting_again_replaces_the_tokens(signed_in, google):
    credential = GoogleCredential.objects.get()
    GoogleCredential.objects.filter(pk=credential.pk).update(
        refresh_token="1//an-older-refresh-token", drive_connected_at=timezone.now()
    )

    connect(signed_in, google)

    credential.refresh_from_db()
    assert credential.refresh_token == REFRESH_TOKEN


@pytest.mark.parametrize(
    ("consent", "result"),
    [
        pytest.param({"sub": "another-google-account"}, "wrong_account", id="another-account"),
        pytest.param({"scope": BASIC_SCOPES}, "not_granted", id="drive-unticked"),
        pytest.param({"refresh_token": None}, "failed", id="no-refresh-token"),
    ],
)
def test_refusals_redirect_with_their_message_and_store_nothing(
    signed_in, credential, google, consent, result, caplog
):
    response = connect(signed_in, google, **consent)

    assert response["Location"] == f"/settings?drive={result}"
    assert_not_connected(credential)
    assert f"Connecting Google Drive failed: user {credential.user.pk}" in caplog.text


def test_cancelling_at_google_returns_cancelled(signed_in):
    flow = start_connecting(signed_in)

    response = callback(signed_in, error="access_denied", state=flow["state"])

    assert response["Location"] == "/settings?drive=cancelled"


def test_a_refused_code_exchange_returns_failed(signed_in, credential, google):
    flow = start_connecting(signed_in)
    fake_google.add_token_error(google, "invalid_grant")

    response = callback(signed_in, code=CODE, state=flow["state"])

    assert response["Location"] == "/settings?drive=failed"
    assert_not_connected(credential)


def test_the_flow_belongs_to_the_user_who_started_it(signed_in, credential, google, caplog):
    flow = start_connecting(signed_in)
    fake_google_consent(google, flow)
    session = signed_in.session
    session[FLOWS_SESSION_KEY][flow["state"]]["user_id"] = UserFactory().pk
    session.save()

    response = callback(signed_in, code=CODE, state=flow["state"])

    assert response["Location"] == "/settings?drive=failed"
    assert "user_changed" in caplog.text
    assert_not_connected(credential)


def test_signing_in_again_keeps_drive_connected(client, google):
    credential = GoogleCredentialFactory(google_sub=SUB, drive=True)
    before = stored_tokens(credential)

    sign_in(client, google)

    assert stored_tokens(credential) == before


def test_signing_in_doesnt_decrypt_the_tokens(client, google, settings):
    GoogleCredentialFactory(google_sub=SUB, drive=True)
    # Without a key, decrypting a token would fail loudly.
    settings.TOKEN_ENCRYPTION_KEY = ""

    assert sign_in(client, google)["Location"] == "/orders"


# Access tokens


def test_not_connected_raises_drive_not_connected(credential):
    with pytest.raises(DriveNotConnected):
        drive_access_token(credential.user)
    with pytest.raises(DriveNotConnected):
        drive_access_token(UserFactory())


def test_a_fresh_access_token_is_reused(google):
    credential = GoogleCredentialFactory(drive=True)

    assert drive_access_token(credential.user) == ACCESS_TOKEN
    assert not google.calls


@pytest.mark.parametrize(
    "expires_in",
    [
        pytest.param(timedelta(seconds=59), id="expiring"),
        pytest.param(timedelta(hours=-1), id="expired"),
    ],
)
def test_an_expiring_access_token_is_refreshed(google, expires_in, caplog):
    credential = GoogleCredentialFactory(
        drive=True, access_token_expires_at=timezone.now() + expires_in
    )
    google.post(
        TOKEN_ENDPOINT,
        json=fake_google.token_response(
            access_token=NEW_ACCESS_TOKEN, id_token=None, scope=DRIVE_SCOPES
        ),
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
    before = timezone.now()

    assert drive_access_token(credential.user) == NEW_ACCESS_TOKEN

    credential.refresh_from_db()
    assert credential.access_token == NEW_ACCESS_TOKEN
    assert stored_tokens(credential)[1].startswith("gAAAAA")
    assert credential.access_token_expires_at >= before + timedelta(seconds=3599)
    assert credential.refresh_token == REFRESH_TOKEN
    assert f"Google Drive access token refreshed: user {credential.user.pk}" in caplog.text


def test_a_new_refresh_token_from_google_replaces_the_old_one(google):
    credential = GoogleCredentialFactory(drive=True, access_token_expires_at=timezone.now())
    fake_google.add_token(google, id_token=None, refresh_token="1//test-new-refresh-token")

    drive_access_token(credential.user)

    credential.refresh_from_db()
    assert credential.refresh_token == "1//test-new-refresh-token"


def test_a_revoked_grant_clears_the_tokens(google, caplog):
    credential = GoogleCredentialFactory(drive=True, access_token_expires_at=timezone.now())
    fake_google.add_token_error(google, "invalid_grant")

    with pytest.raises(DriveAccessRevoked):
        drive_access_token(credential.user)

    assert_not_connected(credential)
    assert f"Google Drive access revoked: user {credential.user.pk}: invalid_grant" in caplog.text


def test_an_unreadable_refresh_token_counts_as_revoked(settings, google):
    credential = GoogleCredentialFactory(drive=True)
    # A new key (G61): the stored tokens can't be decrypted.
    settings.TOKEN_ENCRYPTION_KEY = "another-key"

    with pytest.raises(DriveAccessRevoked):
        drive_access_token(credential.user)

    assert_not_connected(credential)
    assert not google.calls


def test_a_server_error_is_retried_once_then_raises_google_unavailable(google):
    credential = GoogleCredentialFactory(drive=True, access_token_expires_at=timezone.now())
    token_endpoint = google.post(TOKEN_ENDPOINT, status=503)
    before = stored_tokens(credential)

    with pytest.raises(GoogleUnavailable):
        drive_access_token(credential.user)

    assert token_endpoint.call_count == 2
    # Google may be back later: the connection stays.
    assert stored_tokens(credential) == before


def test_a_refresh_cant_bring_back_tokens_cleared_meanwhile(google):
    credential = GoogleCredentialFactory(drive=True, access_token_expires_at=timezone.now())

    def disconnected_during_the_refresh(request):
        # Another request disconnects Drive while this refresh waits for Google.
        GoogleCredential.objects.filter(pk=credential.pk).update(**DRIVE_DISCONNECTED)
        body = fake_google.token_response(access_token=NEW_ACCESS_TOKEN, id_token=None)
        return 200, {}, json.dumps(body)

    google.add_callback(responses.POST, TOKEN_ENDPOINT, callback=disconnected_during_the_refresh)

    drive_access_token(credential.user)

    assert_not_connected(credential)


# Disconnecting


def test_disconnecting_revokes_at_google_and_clears_the_tokens(client, google, caplog):
    credential = GoogleCredentialFactory(drive=True)
    client.force_login(credential.user)
    revocation = google.post(
        REVOCATION_ENDPOINT, match=[matchers.urlencoded_params_matcher({"token": REFRESH_TOKEN})]
    )

    response = client.delete(DRIVE_URL)

    assert response.status_code == 204
    assert revocation.call_count == 1
    assert_not_connected(credential)
    assert f"Google Drive disconnected: user {credential.user.pk}" in caplog.text
    assert not client.get("/api/auth/session/").json()["user"]["google_drive_connected"]


def test_disconnecting_clears_the_tokens_even_when_revoking_fails(client, google, caplog):
    credential = GoogleCredentialFactory(drive=True)
    client.force_login(credential.user)
    google.post(REVOCATION_ENDPOINT, status=503)

    response = client.delete(DRIVE_URL)

    assert response.status_code == 204
    assert_not_connected(credential)
    assert "Revoking Google Drive access at Google failed" in caplog.text


def test_disconnecting_without_drive_does_nothing(signed_in, google):
    assert signed_in.delete(DRIVE_URL).status_code == 204
    assert not google.calls


def test_disconnecting_needs_a_signed_in_user(client):
    assert client.delete(DRIVE_URL).status_code == 401


def test_disconnecting_needs_the_csrf_token(google):
    credential = GoogleCredentialFactory(drive=True)
    client = Client(enforce_csrf_checks=True)
    client.force_login(credential.user)
    client.get("/api/auth/session/")  # Sets the CSRF cookie, as the app's first request does.

    response = client.delete(DRIVE_URL)

    assert response.status_code == 403
    assert not google.calls
    assert GoogleCredential.objects.get().drive_connected_at is not None


# Logs


def test_logs_hold_no_token_code_state_or_email(signed_in, credential, google, caplog):
    caplog.set_level(logging.DEBUG)
    flow = start_connecting(signed_in)
    fake_google_consent(google, flow)
    callback(signed_in, code=CODE, state=flow["state"])
    GoogleCredential.objects.filter(pk=credential.pk).update(access_token_expires_at=timezone.now())
    fake_google.add_token(google, access_token=NEW_ACCESS_TOKEN, id_token=None)
    drive_access_token(credential.user)
    fake_google.add_revoke(google)
    signed_in.delete(DRIVE_URL)

    assert f"Google Drive connected: user {credential.user.pk}" in caplog.text
    assert "refreshed" in caplog.text
    assert "disconnected" in caplog.text
    secrets = [CODE, flow["state"], flow["nonce"], ACCESS_TOKEN, NEW_ACCESS_TOKEN, REFRESH_TOKEN]
    for secret in [*secrets, credential.user.email, "gAAAAA"]:
        assert secret not in caplog.text
