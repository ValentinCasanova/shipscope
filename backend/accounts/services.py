"""Signing in with a Google account, and the Google Drive access a user connects."""

import functools
import logging
from collections.abc import Iterable
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.utils import timezone

from integrations.google import (
    DRIVE_FILE_SCOPE,
    GoogleIdentity,
    GoogleOAuthClient,
    GoogleOAuthConfig,
    GoogleOAuthError,
    InvalidGrant,
    TokenResponse,
)

from .fields import encryption_configured
from .models import GoogleCredential, User

logger = logging.getLogger(__name__)

# The length of Django's first_name and last_name columns.
NAME_MAX_LENGTH = 150
# A stored access token is used until this long before it expires, so it can't expire
# while a request to Google is on its way.
ACCESS_TOKEN_MARGIN = timedelta(seconds=60)
# What a credential holds while Google Drive isn't connected.
DRIVE_DISCONNECTED: dict[str, Any] = {
    "refresh_token": "",
    "access_token": "",
    "access_token_expires_at": None,
    "granted_scopes": "",
    "drive_connected_at": None,
}


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


# Signing in


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
        # Signing in doesn't need Drive's tokens, so it doesn't decrypt them.
        .defer("refresh_token", "access_token")
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


def google_account_id(user: User) -> str | None:
    """The ID (sub) of the Google account the user signs in with, or None for a user who
    doesn't sign in with Google, such as the admin."""
    return GoogleCredential.objects.filter(user=user).values_list("google_sub", flat=True).first()


# Google Drive (drive.file: only the files the user opens with ShipScope)
#
# Connecting stores Google's refresh token and the first access token, encrypted
# (fields.py). drive_access_token() is the only way to use them: callers never read the
# model's token fields.


class DriveNotConnected(Exception):
    """The user hasn't connected Google Drive, or disconnected it."""


class DriveAccessRevoked(DriveNotConnected):
    """Google no longer accepts the stored grant, or it can't be decrypted (G59, G61).

    The user removed ShipScope's access, or Google ended it. The tokens are cleared, so
    the user can connect Google Drive again.
    """


class DriveConnectionRefused(Exception):
    """Google's answer can't connect Google Drive for this user.

    result is what the app shows (?drive=<result>), and the message the reason logged.
    """

    def __init__(self, result: str, reason: str) -> None:
        super().__init__(reason)
        self.result = result


def drive_configured() -> bool:
    """Whether connecting Google Drive can work: an OAuth client, and a key for its tokens."""
    return google_config().configured and encryption_configured()


def drive_connected(user: User) -> bool:
    """Whether the user has connected Google Drive. Decrypts nothing."""
    return GoogleCredential.objects.filter(user=user, drive_connected_at__isnull=False).exists()


def connect_drive(user: User, identity: GoogleIdentity, tokens: TokenResponse) -> None:
    """Store the Drive access Google granted after the user's consent.

    Refuses three answers, with DriveConnectionRefused:
    - another Google account than the one the user signs in with
    - a grant without drive.file, which users can untick on Google's consent screen
    - no refresh token (G60): the access token alone stops working within the hour

    Connecting again replaces the tokens. The old grant isn't revoked: revoking a token
    ends every token of the user's grant to ShipScope, the new ones included.
    """
    google_sub = google_account_id(user)
    if google_sub is None:
        raise DriveConnectionRefused("failed", "no_google_account")
    if identity.sub != google_sub:
        raise DriveConnectionRefused("wrong_account", "wrong_account")
    if DRIVE_FILE_SCOPE not in tokens.scopes:
        raise DriveConnectionRefused("not_granted", "drive_file_not_granted")
    if not tokens.refresh_token:
        raise DriveConnectionRefused("failed", "no_refresh_token")

    now = timezone.now()
    GoogleCredential.objects.filter(user=user).update(
        refresh_token=tokens.refresh_token,
        access_token=tokens.access_token,
        # Google issued it moments ago. ACCESS_TOKEN_MARGIN covers the difference.
        access_token_expires_at=now + timedelta(seconds=tokens.expires_in),
        granted_scopes=_scopes_text(tokens.scopes),
        drive_connected_at=now,
        updated_at=now,
    )


def drive_access_token(user: User) -> str:
    """An access token to the user's Google Drive, valid for at least another minute.

    The stored one while it lasts, otherwise a new one from Google, which is stored in
    its place. Raises DriveNotConnected if the user hasn't connected Drive, and
    DriveAccessRevoked if Google refuses the grant, whose tokens are then cleared.
    GoogleUnavailable means Google couldn't be reached, and trying later may work.
    """
    credential = (
        GoogleCredential.objects.filter(user=user, drive_connected_at__isnull=False)
        .only("refresh_token", "access_token", "access_token_expires_at", "drive_connected_at")
        .first()
    )
    if credential is None:
        raise DriveNotConnected
    if not credential.refresh_token:
        # Stored, but it can't be decrypted: the key changed (G61).
        raise _access_revoked(credential, user, "unreadable_refresh_token")

    expires_at = credential.access_token_expires_at
    if credential.access_token and expires_at and timezone.now() < expires_at - ACCESS_TOKEN_MARGIN:
        return credential.access_token

    requested_at = timezone.now()
    try:
        tokens = google_client().refresh(credential.refresh_token)
    except InvalidGrant:
        raise _access_revoked(credential, user, "invalid_grant") from None

    refreshed: dict[str, Any] = {
        "access_token": tokens.access_token,
        # Counted from before the request, so the real expiry is a little later.
        "access_token_expires_at": requested_at + timedelta(seconds=tokens.expires_in),
        "updated_at": timezone.now(),
    }
    if tokens.scopes:
        refreshed["granted_scopes"] = _scopes_text(tokens.scopes)
    if tokens.refresh_token:
        # Google may replace the refresh token, and then the old one stops working.
        refreshed["refresh_token"] = tokens.refresh_token
    _this_connection(credential).update(**refreshed)
    logger.info("Google Drive access token refreshed: user %s", user.pk)
    return tokens.access_token


def disconnect_drive(user: User) -> None:
    """Revoke ShipScope's access at Google, and clear the stored tokens.

    Revoking ends every token of the user's grant to ShipScope. The tokens are cleared
    even when Google can't be reached, since the user asked ShipScope to stop using them.
    Disconnecting a user who hasn't connected Drive does nothing.
    """
    credential = (
        GoogleCredential.objects.filter(user=user, drive_connected_at__isnull=False)
        .only("refresh_token", "access_token")
        .first()
    )
    if credential is None:
        return
    token = credential.refresh_token or credential.access_token
    if token:
        try:
            google_client().revoke(token)
        except GoogleOAuthError as failure:
            logger.warning(
                "Revoking Google Drive access at Google failed, clearing the tokens anyway: "
                "user %s: %s: %s",
                user.pk,
                type(failure).__name__,
                failure,
            )
    GoogleCredential.objects.filter(pk=credential.pk).update(
        **DRIVE_DISCONNECTED, updated_at=timezone.now()
    )
    logger.info("Google Drive disconnected: user %s", user.pk)


def _this_connection(credential: GoogleCredential) -> QuerySet[GoogleCredential]:
    """The credential's row while its Drive connection is still the one loaded.

    Connecting again or disconnecting changes drive_connected_at, so an update through
    this queryset can't bring back tokens that were cleared in the meantime, or clear
    newer ones.
    """
    return GoogleCredential.objects.filter(
        pk=credential.pk, drive_connected_at=credential.drive_connected_at
    )


def _access_revoked(credential: GoogleCredential, user: User, reason: str) -> DriveAccessRevoked:
    """Clear the tokens Google no longer accepts, and return the exception that says so."""
    _this_connection(credential).update(**DRIVE_DISCONNECTED, updated_at=timezone.now())
    logger.warning("Google Drive access revoked: user %s: %s", user.pk, reason)
    return DriveAccessRevoked(reason)


def _scopes_text(scopes: Iterable[str]) -> str:
    return " ".join(sorted(scopes))
