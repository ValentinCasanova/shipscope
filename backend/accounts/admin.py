from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import formats, timezone

from .models import GoogleCredential, User

# Google Drive access stays out of the admin. Its forms and lists show only whether Drive
# is connected, and its queries don't load the tokens, so it never decrypts one, and
# saving a form leaves them as they are.
TOKEN_FIELDS = ["refresh_token", "access_token"]
DRIVE_FIELDS = [*TOKEN_FIELDS, "access_token_expires_at", "granted_scopes", "drive_connected_at"]


@admin.display(description="Google Drive")
def google_drive(credential: GoogleCredential) -> str:
    if credential.drive_connected_at is None:
        return "Not connected"
    connected_at = formats.localize(timezone.localtime(credential.drive_connected_at))
    return f"Connected since {connected_at}"


class GoogleCredentialInline(admin.StackedInline):
    model = GoogleCredential
    exclude = DRIVE_FIELDS
    readonly_fields = [google_drive, "created_at", "updated_at"]

    def get_queryset(self, request: HttpRequest) -> QuerySet[GoogleCredential]:
        return super().get_queryset(request).defer(*TOKEN_FIELDS)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = [GoogleCredentialInline]


@admin.register(GoogleCredential)
class GoogleCredentialAdmin(admin.ModelAdmin):
    list_display = ["user", "google_sub", "sheet_id", google_drive, "created_at"]
    list_select_related = ["user"]
    search_fields = ["user__username", "user__email", "google_sub"]
    ordering = ["-created_at"]
    exclude = DRIVE_FIELDS
    readonly_fields = [google_drive, "created_at", "updated_at"]

    def get_queryset(self, request: HttpRequest) -> QuerySet[GoogleCredential]:
        return super().get_queryset(request).defer(*TOKEN_FIELDS)
