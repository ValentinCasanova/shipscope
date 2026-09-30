"""Test data for users and their Google accounts, shared with the other apps' tests."""

from datetime import timedelta

import factory
from django.conf import settings
from django.utils import timezone

from accounts.models import GoogleCredential
from integrations.tests.fake_google import ACCESS_TOKEN, DRIVE_SCOPES, REFRESH_TOKEN


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = settings.AUTH_USER_MODEL

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda user: f"{user.username}@example.com")
    # An unusable password, like a user who only signs in with Google, and no hashing,
    # which takes Django's default hasher about 0.4 seconds per password. Pass
    # password="…" for a user who can sign in with one.
    password = factory.django.Password(None)


class GoogleCredentialFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GoogleCredential

    class Params:
        # GoogleCredentialFactory(drive=True): Google Drive connected, with an access
        # token valid for another hour. Storing the tokens needs TOKEN_ENCRYPTION_KEY.
        drive = factory.Trait(
            refresh_token=REFRESH_TOKEN,
            access_token=ACCESS_TOKEN,
            access_token_expires_at=factory.LazyFunction(
                lambda: timezone.now() + timedelta(hours=1)
            ),
            granted_scopes=DRIVE_SCOPES,
            drive_connected_at=factory.LazyFunction(timezone.now),
        )

    user = factory.SubFactory(UserFactory)
    # Real IDs are strings of 21 digits.
    google_sub = factory.Sequence(lambda n: str(10**20 + n))
