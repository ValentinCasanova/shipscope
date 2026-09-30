"""The accounts admin shows whether Google Drive is connected, and never a token.

config/tests/test_admin.py already renders each model's list, search, and add pages.
"""

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains, assertNotContains

from integrations.tests.fake_google import ACCESS_TOKEN, REFRESH_TOKEN

from .factories import GoogleCredentialFactory
from .test_fields import stored_tokens

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "url",
    [
        pytest.param(lambda c: reverse("admin:accounts_googlecredential_changelist"), id="list"),
        pytest.param(
            lambda c: reverse("admin:accounts_googlecredential_change", args=[c.pk]),
            id="credential",
        ),
        pytest.param(lambda c: reverse("admin:accounts_user_change", args=[c.user.pk]), id="user"),
    ],
)
def test_pages_show_drive_status_but_no_token(superuser_client, url):
    credential = GoogleCredentialFactory(drive=True)

    response = superuser_client.get(url(credential))

    assertContains(response, "Connected since")
    for secret in [REFRESH_TOKEN, ACCESS_TOKEN, *stored_tokens(credential), "gAAAAA"]:
        assertNotContains(response, secret)


def test_a_credential_without_drive_shows_not_connected(superuser_client):
    credential = GoogleCredentialFactory()

    response = superuser_client.get(
        reverse("admin:accounts_googlecredential_change", args=[credential.pk])
    )

    assertContains(response, "Not connected")


def test_saving_a_credential_leaves_its_tokens_as_they_were(superuser_client):
    credential = GoogleCredentialFactory(drive=True)
    before = stored_tokens(credential)

    response = superuser_client.post(
        reverse("admin:accounts_googlecredential_change", args=[credential.pk]),
        {"user": credential.user.pk, "google_sub": credential.google_sub, "sheet_id": "a-sheet"},
    )

    assert response.status_code == 302
    credential.refresh_from_db()
    assert credential.sheet_id == "a-sheet"
    # Not even encrypted again: each encryption of a token gives another ciphertext.
    assert stored_tokens(credential) == before
