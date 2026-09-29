import pytest
from django.db import IntegrityError

from accounts import services
from accounts.models import User
from integrations.google import GoogleIdentity

pytestmark = pytest.mark.django_db

IDENTITY = GoogleIdentity(
    sub="109876543210987654321",
    email="ada@example.com",
    email_verified=True,
    given_name="Ada",
    family_name="Lovelace",
)


def test_first_sign_in_creates_the_user_and_credential():
    user, created = services.sign_in_with_google(IDENTITY)

    assert created
    assert user.google_credential.google_sub == IDENTITY.sub
    assert not user.has_usable_password()


def test_second_sign_in_finds_the_same_user():
    first, _ = services.sign_in_with_google(IDENTITY)

    second, created = services.sign_in_with_google(IDENTITY)

    assert second == first
    assert not created


def test_long_names_are_cut_to_fit():
    identity = GoogleIdentity(**{**IDENTITY.__dict__, "given_name": "A" * 200})

    user, _ = services.sign_in_with_google(identity)

    assert user.first_name == "A" * 150


def test_a_simultaneous_first_sign_in_finds_the_user_the_other_created(monkeypatch):
    real_sign_in = services._sign_in
    calls = []

    def racing_sign_in(identity):
        calls.append(identity)
        if len(calls) == 1:
            # The other request creates the user while this one is still deciding to.
            real_sign_in(identity)
            raise IntegrityError("duplicate key value violates unique constraint")
        return real_sign_in(identity)

    monkeypatch.setattr(services, "_sign_in", racing_sign_in)

    user, created = services.sign_in_with_google(IDENTITY)

    assert not created
    assert User.objects.get() == user
