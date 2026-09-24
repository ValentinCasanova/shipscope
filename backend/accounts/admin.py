from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import GoogleCredential, User


class GoogleCredentialInline(admin.StackedInline):
    model = GoogleCredential
    readonly_fields = ["created_at", "updated_at"]


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    inlines = [GoogleCredentialInline]


@admin.register(GoogleCredential)
class GoogleCredentialAdmin(admin.ModelAdmin):
    list_display = ["user", "google_sub", "sheet_id", "created_at"]
    list_select_related = ["user"]
    search_fields = ["user__username", "user__email", "google_sub"]
    ordering = ["-created_at"]
    readonly_fields = ["created_at", "updated_at"]
