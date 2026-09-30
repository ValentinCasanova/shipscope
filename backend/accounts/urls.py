from django.urls import path

from . import views

urlpatterns = [
    path("auth/google/login/", views.google_login, name="google-login"),
    path("auth/google/callback/", views.google_callback, name="google-callback"),
    path("auth/session/", views.SessionView.as_view(), name="session"),
    path("auth/google/drive/connect/", views.google_drive_connect, name="google-drive-connect"),
    path("auth/google/drive/", views.GoogleDriveView.as_view(), name="google-drive"),
]
