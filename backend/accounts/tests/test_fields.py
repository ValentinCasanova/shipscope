"""EncryptedTextField: the database holds only ciphertext, and code sees plain text."""

import logging

import pytest
from cryptography.fernet import InvalidToken
from django.core.exceptions import FieldError, ImproperlyConfigured
from django.db import connection

from accounts.fields import decrypt, encrypt
from accounts.models import GoogleCredential
from integrations.tests.fake_google import ACCESS_TOKEN, REFRESH_TOKEN

from .factories import GoogleCredentialFactory

pytestmark = pytest.mark.django_db


def stored_tokens(credential: GoogleCredential) -> tuple[str, str]:
    """The refresh and access token columns, as the database holds them."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT refresh_token, access_token FROM accounts_googlecredential WHERE id = %s",
            [credential.pk],
        )
        return cursor.fetchone()


def reloaded(credential: GoogleCredential) -> GoogleCredential:
    return GoogleCredential.objects.get(pk=credential.pk)


def test_the_database_holds_only_ciphertext():
    credential = GoogleCredentialFactory(drive=True)

    refresh_token, access_token = stored_tokens(credential)

    # Fernet's version byte and timestamp, in URL-safe base64.
    assert refresh_token.startswith("gAAAAA")
    assert access_token.startswith("gAAAAA")
    assert REFRESH_TOKEN not in refresh_token
    assert ACCESS_TOKEN not in access_token


def test_values_round_trip():
    credential = GoogleCredentialFactory(drive=True)

    loaded = reloaded(credential)

    assert (loaded.refresh_token, loaded.access_token) == (REFRESH_TOKEN, ACCESS_TOKEN)


def test_a_queryset_update_encrypts_too():
    credential = GoogleCredentialFactory()

    GoogleCredential.objects.filter(pk=credential.pk).update(access_token=ACCESS_TOKEN)

    assert stored_tokens(credential)[1].startswith("gAAAAA")
    assert reloaded(credential).access_token == ACCESS_TOKEN


def test_empty_stays_empty_without_a_key(settings):
    settings.TOKEN_ENCRYPTION_KEY = ""
    credential = GoogleCredentialFactory()

    assert stored_tokens(credential) == ("", "")
    assert reloaded(credential).refresh_token == ""


def test_the_same_text_encrypts_differently_each_time():
    assert encrypt(REFRESH_TOKEN) != encrypt(REFRESH_TOKEN)


def test_the_wrong_key_raises_invalid_token(settings):
    ciphertext = encrypt(REFRESH_TOKEN)
    settings.TOKEN_ENCRYPTION_KEY = "another-key"

    with pytest.raises(InvalidToken):
        decrypt(ciphertext)


def test_a_value_from_another_key_loads_as_empty_with_a_warning(settings, caplog):
    credential = GoogleCredentialFactory(drive=True)
    settings.TOKEN_ENCRYPTION_KEY = "another-key"

    loaded = reloaded(credential)

    assert (loaded.refresh_token, loaded.access_token) == ("", "")
    assert "accounts.GoogleCredential.refresh_token can't be decrypted" in caplog.text
    assert caplog.records[0].levelno == logging.WARNING
    for secret in [REFRESH_TOKEN, *stored_tokens(credential)]:
        assert secret not in caplog.text


def test_an_altered_value_loads_as_empty():
    credential = GoogleCredentialFactory(drive=True)
    ciphertext = stored_tokens(credential)[0]
    # One character changed: the HMAC check fails, so nothing is decrypted.
    altered = ciphertext[:-5] + ("A" if ciphertext[-5] != "A" else "B") + ciphertext[-4:]
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE accounts_googlecredential SET refresh_token = %s WHERE id = %s",
            [altered, credential.pk],
        )

    assert reloaded(credential).refresh_token == ""


def test_saving_a_token_without_a_key_fails_loudly(settings):
    settings.TOKEN_ENCRYPTION_KEY = ""
    credential = GoogleCredentialFactory()

    # An update, which reads nothing back, so only the way to the database is tested.
    with pytest.raises(ImproperlyConfigured, match="TOKEN_ENCRYPTION_KEY is empty"):
        GoogleCredential.objects.filter(pk=credential.pk).update(refresh_token=REFRESH_TOKEN)


def test_loading_a_token_without_a_key_fails_loudly(settings):
    credential = GoogleCredentialFactory(drive=True)
    settings.TOKEN_ENCRYPTION_KEY = ""

    with pytest.raises(ImproperlyConfigured, match="TOKEN_ENCRYPTION_KEY is empty"):
        reloaded(credential)


def test_whether_a_token_is_empty_can_be_queried():
    GoogleCredentialFactory(drive=True)
    GoogleCredentialFactory()

    assert GoogleCredential.objects.filter(refresh_token="").count() == 1
    assert GoogleCredential.objects.exclude(refresh_token="").count() == 1


@pytest.mark.parametrize(
    "lookup",
    [{"refresh_token": REFRESH_TOKEN}, {"refresh_token__startswith": "1//"}],
    ids=["exact", "startswith"],
)
def test_other_lookups_raise_instead_of_finding_nothing(lookup):
    with pytest.raises(FieldError):
        GoogleCredential.objects.filter(**lookup).exists()
