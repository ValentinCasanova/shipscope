"""Django settings for the ShipScope API.

Environment-specific values come from environment variables. Secrets have no
defaults, and DEBUG stays off unless it is explicitly enabled.
"""

import logging
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

from .ecs import task_private_ips
from .logs import FORMATTERS

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()

# Commands run on the host (manage.py, pytest) load the repo-root .env. Variables
# already set in the environment take precedence and a missing file is ignored, so
# containers, which receive their environment from the runtime, are unaffected.
environ.Env.read_env(BASE_DIR.parent / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
# An unset variable already fails above. Django only rejects an empty key when something
# first uses it, such as signing a session, so without this check an empty value (as in a
# freshly copied .env) would start without errors.
if not SECRET_KEY:
    raise ImproperlyConfigured("The DJANGO_SECRET_KEY environment variable is empty")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
# On ECS, also the task's private IP, which load balancer health checks use as the host.
ALLOWED_HOSTS = [*env.list("DJANGO_ALLOWED_HOSTS", default=[]), *task_private_ips()]


# HTTPS

# Browsers then send these cookies only over HTTPS. Local development uses plain HTTP,
# with DEBUG on.
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# In AWS, CloudFront handles HTTPS and reaches the app over plain HTTP, so Django can't
# tell on its own that the browser used HTTPS. CloudFront sends the viewer's protocol in
# CloudFront-Forwarded-Proto, and it redirects plain-HTTP viewers instead of forwarding
# their requests. Only CloudFront can reach the load balancer, so no client can set this
# header on a plain-HTTP request. Trusting it makes request.is_secure() true, so Django's
# CSRF check accepts the browser's https:// Origin.
if env.bool("DJANGO_BEHIND_CLOUDFRONT", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_CLOUDFRONT_FORWARDED_PROTO", "https")
    # CloudFront also does the HTTPS redirect and adds the HSTS header, the two things
    # these deployment checks want Django to do.
    SILENCED_SYSTEM_CHECKS = ["security.W004", "security.W008"]


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serves collected static files (admin, DRF browsable API) behind Gunicorn.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# The POSTGRES_* names match the variables the official Postgres image reads.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="shipscope"),
        "USER": env("POSTGRES_USER", default="shipscope"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST", default="localhost"),
        "PORT": env.int("POSTGRES_PORT", default=5432),
        "OPTIONS": {
            # Fail within seconds when the database is unreachable, instead of waiting
            # minutes for the operating system's TCP connect timeout.
            "connect_timeout": 5,
            # "prefer" uses TLS when the server offers it, which the local Postgres
            # container doesn't. AWS sets "require", so the connection to RDS is never
            # unencrypted. Neither checks the server's certificate; "verify-full" would
            # also need RDS's certificate bundle in the image.
            "sslmode": env("POSTGRES_SSLMODE", default="prefer"),
        },
    },
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = "static/"
# collectstatic copies files here; WhiteNoise serves them in production.
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Django REST framework

REST_FRAMEWORK = {
    # Secure by default: every endpoint requires an authenticated user unless the
    # view explicitly opts out.
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}


# Logging
# Django's default config only prints to the console while DEBUG is on, which would
# hide production errors. Send INFO and above to stdout, where container logs are read,
# in the format DJANGO_LOG_FORMAT picks (see logs.py).

log_format = env("DJANGO_LOG_FORMAT", default="plain")
if log_format not in FORMATTERS:
    raise ImproperlyConfigured(
        f"DJANGO_LOG_FORMAT must be one of {', '.join(FORMATTERS)}, not {log_format!r}"
    )
if log_format == "json":
    # Python warnings would otherwise print as plain text to stderr.
    logging.captureWarnings(True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": FORMATTERS,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": log_format,
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        # Replace Django's DEBUG-only handlers instead of adding a second console
        # handler, so every record is printed exactly once.
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
