"""Test data for users and their Google accounts, shared with the other apps' tests."""

import factory
from django.conf import settings

from accounts.models import GoogleCredential


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

    user = factory.SubFactory(UserFactory)
    # Real IDs are strings of 21 digits.
    google_sub = factory.Sequence(lambda n: str(10**20 + n))
