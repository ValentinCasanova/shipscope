"""The session endpoint, and how the API treats signed-out requests."""

import base64

import pytest
from django.test import Client

from .factories import GoogleCredentialFactory, UserFactory

SESSION_URL = "/api/auth/session/"

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return UserFactory(first_name="Ada", last_name="Lovelace", email="ada@example.com")


def test_signed_out_gets_a_null_user_and_the_csrf_cookie(client):
    response = client.get(SESSION_URL)

    assert response.status_code == 200
    assert response.json() == {"user": None}
    assert "csrftoken" in response.cookies
    assert "no-store" in response["Cache-Control"]


def test_signed_in_gets_the_user(client, user):
    client.force_login(user)

    response = client.get(SESSION_URL)

    assert response.json() == {
        "user": {
            "id": user.pk,
            "email": "ada@example.com",
            "name": "Ada Lovelace",
            "google_drive_connected": False,
        }
    }


def test_the_user_shows_whether_google_drive_is_connected(client):
    credential = GoogleCredentialFactory(drive=True)
    client.force_login(credential.user)

    assert client.get(SESSION_URL).json()["user"]["google_drive_connected"] is True


def test_a_user_without_a_name_is_named_by_email(client):
    client.force_login(UserFactory(email="ada@example.com"))

    assert client.get(SESSION_URL).json()["user"]["name"] == "ada@example.com"


def test_signed_out_api_requests_get_401(client):
    response = client.delete(SESSION_URL)

    assert response.status_code == 401
    assert response["WWW-Authenticate"] == 'Session realm="api"'


def test_basic_authentication_is_ignored(client):
    UserFactory(username="ada", password="correct-horse")
    basic = {"Authorization": "Basic " + base64.b64encode(b"ada:correct-horse").decode()}

    assert client.get(SESSION_URL, headers=basic).json() == {"user": None}
    assert client.delete(SESSION_URL, headers=basic).status_code == 401


def test_sign_out_needs_the_csrf_token(user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    client.get(SESSION_URL)  # Sets the CSRF cookie, as the app's first request does.

    without_token = client.delete(SESSION_URL)
    with_token = client.delete(
        SESSION_URL, headers={"X-CSRFToken": client.cookies["csrftoken"].value}
    )

    assert without_token.status_code == 403
    assert "CSRF" in without_token.json()["detail"]
    assert with_token.status_code == 204
    assert client.get(SESSION_URL).json() == {"user": None}


def test_sign_out_ends_the_session_on_the_server(user):
    client = Client()
    client.force_login(user)
    session_id = client.cookies["sessionid"].value

    client.delete(SESSION_URL)

    # The old cookie no longer signs anyone in, even if a copy of it survives.
    replay = Client()
    replay.cookies["sessionid"] = session_id
    assert replay.get(SESSION_URL).json() == {"user": None}
