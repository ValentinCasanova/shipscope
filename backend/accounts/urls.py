from django.urls import path

from . import views

urlpatterns = [
    path("auth/google/login/", views.google_login, name="google-login"),
    path("auth/google/callback/", views.google_callback, name="google-callback"),
    path("auth/session/", views.SessionView.as_view(), name="session"),
]
