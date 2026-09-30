"""Users, and the Google accounts they sign in with."""

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from .fields import EncryptedTextField


class User(AbstractUser):
    """A ShipScope user: Django's default user, with nothing added yet.

    Django recommends a custom user model even when the default one is enough, because
    AUTH_USER_MODEL can't simply be switched once other tables reference the user. With
    this model in place from the first migration, a field such as a unique email can be
    added later with an ordinary migration.

    Models refer to it as settings.AUTH_USER_MODEL, and other code gets it from
    get_user_model(), so nothing depends on which class it is.
    """


class GoogleCredential(models.Model):
    """Links a user to their Google account, their Google Drive access, and the Sheet of
    orders they connected.

    Drive access is Google's refresh token and the current access token, both encrypted
    (fields.py). Both are blank until the user connects Google Drive, and only the Drive
    functions in services.py read them.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="google_credential"
    )
    # Sign-in finds returning users by this ID, not by email: an account's email address
    # can change, its ID can't.
    google_sub = models.CharField(
        "Google account ID",
        max_length=255,
        help_text="The sub claim of the account's Google ID token.",
    )
    sheet_id = models.CharField(
        "Sheet ID", max_length=128, blank=True, help_text="Blank until a Sheet is connected."
    )
    # Google Drive access. The text columns also default to blank in the database, so the
    # release before them can still create credentials while a release rolls out.
    refresh_token = EncryptedTextField(
        blank=True,
        default="",
        db_default="",
        help_text="Google's refresh token, which gets new access tokens.",
    )
    access_token = EncryptedTextField(
        blank=True,
        default="",
        db_default="",
        help_text="The last access token, valid for about an hour.",
    )
    access_token_expires_at = models.DateTimeField(null=True, blank=True)
    granted_scopes = models.TextField(
        blank=True,
        default="",
        db_default="",
        help_text="The scopes Google last reported, separated by spaces.",
    )
    drive_connected_at = models.DateTimeField(
        "Google Drive connected at",
        null=True,
        blank=True,
        help_text="When the user connected Google Drive. Empty while it isn't connected.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["google_sub"],
                name="accounts_googlecredential_google_sub_unique",
                # Model validation, and so the admin, then shows the message on the field.
                violation_error_code="unique",
                violation_error_message="This Google account is already linked to another user.",
            ),
            models.CheckConstraint(
                condition=~models.Q(google_sub=""),
                name="accounts_googlecredential_google_sub_not_empty",
                violation_error_message="The Google account ID can't be empty.",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user} ({self.google_sub})"
