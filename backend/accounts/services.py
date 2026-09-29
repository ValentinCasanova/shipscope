"""Signing in with a Google account."""

import functools

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

from integrations.google import GoogleIdentity, GoogleOAuthClient, GoogleOAuthConfig

from .models import GoogleCredential, User

# The length of Django's first_name and last_name columns.
NAME_MAX_LENGTH = 150


def google_config() -> GoogleOAuthConfig:
    """This environment's OAuth client, from the settings."""
    return GoogleOAuthConfig(settings.GOOGLE_OAUTH_CLIENT_ID, settings.GOOGLE_OAUTH_CLIENT_SECRET)


def google_client() -> GoogleOAuthClient:
    """The Google OAuth client for this environment's settings.

    One client per configuration, kept for the life of the process, so Google's signing
    keys stay cached between requests.
    """
    return _client_for(google_config())


@functools.cache
def _client_for(config: GoogleOAuthConfig) -> GoogleOAuthClient:
    return GoogleOAuthClient(config)


def sign_in_with_google(identity: GoogleIdentity) -> tuple[User, bool]:
    """The user of this Google account, created on its first sign-in.

    Users are found by the account's ID (sub), never by email: an email address can
    change, and can later belong to someone else. The name and email are copied from
    Google at every sign-in. Returns the user, and whether it was just created.
    """
    try:
        return _sign_in(identity)
    except IntegrityError:
        # The same account's first sign-in ran twice at once, and the other one created
        # the user first. This time, it's found.
        return _sign_in(identity)


@transaction.atomic
def _sign_in(identity: GoogleIdentity) -> tuple[User, bool]:
    credential = (
        GoogleCredential.objects.select_related("user")
        .select_for_update()
        .filter(google_sub=identity.sub)
        .first()
    )
    created = credential is None
    if credential is None:
        # A username is required and must be unique, and nobody sees it but the admin.
        user = get_user_model()(username=f"google-{identity.sub}")
        # Only Google signs this user in; Django's password login refuses them.
        user.set_unusable_password()
    else:
        user = credential.user

    user.email = identity.email
    user.first_name = identity.given_name[:NAME_MAX_LENGTH]
    user.last_name = identity.family_name[:NAME_MAX_LENGTH]
    user.save()
    if created:
        GoogleCredential.objects.create(user=user, google_sub=identity.sub)
    return user, created
