"""Users, and the Google accounts they sign in with."""

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


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
    """Links a user to their Google account and to the Sheet of orders they connected.

    No OAuth tokens are stored yet. They arrive with the Google sign-in flow, together with
    their encryption.
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
