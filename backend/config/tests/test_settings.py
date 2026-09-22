import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

from .ecs_metadata import TASK_IP

BACKEND_DIR = Path(__file__).resolve().parents[2]

CLOUDFRONT_HOST = "d111111abcdef8.cloudfront.net"

# What the ECS task definition sets, apart from the database connection details.
DEPLOYED_ENVIRONMENT = {
    "DJANGO_DEBUG": "false",
    "DJANGO_ALLOWED_HOSTS": CLOUDFRONT_HOST,
    "DJANGO_BEHIND_CLOUDFRONT": "true",
    # The deployment checks reject keys shorter than 50 characters.
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(50),
    "POSTGRES_SSLMODE": "require",
}


def run_in_new_process(args: list[str], **environment: str) -> subprocess.CompletedProcess[str]:
    """Load the settings in a new process, the way a container loads them at startup."""
    # Nothing here connects to the database, but the settings require a password.
    env = {
        **os.environ,
        "DJANGO_SECRET_KEY": "test-secret-key",
        "POSTGRES_PASSWORD": "unused",
        **environment,
    }
    # The tests pass fixed arguments, never outside input.
    return subprocess.run(  # noqa: S603
        [sys.executable, *args],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def load_settings(*names: str, **environment: str) -> dict:
    """Return the named settings as a new process with this environment loads them."""
    script = (
        "import json; from django.conf import settings; "
        f"print(json.dumps({{name: getattr(settings, name, None) for name in {names!r}}}))"
    )
    result = run_in_new_process(
        ["-c", script], DJANGO_SETTINGS_MODULE="config.settings", **environment
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_starts_with_a_secret_key():
    result = run_in_new_process(["manage.py", "check"])

    assert result.returncode == 0, result.stderr


def test_fails_at_startup_when_secret_key_is_empty():
    result = run_in_new_process(["manage.py", "check"], DJANGO_SECRET_KEY="")

    assert result.returncode != 0
    assert "The DJANGO_SECRET_KEY environment variable is empty" in result.stderr


def test_allows_the_task_ip_on_ecs(metadata_endpoint):
    loaded = load_settings("ALLOWED_HOSTS", DJANGO_ALLOWED_HOSTS=CLOUDFRONT_HOST)

    assert loaded["ALLOWED_HOSTS"] == [CLOUDFRONT_HOST, TASK_IP]


def test_trusts_cloudfronts_protocol_header_only_behind_cloudfront():
    behind = load_settings("SECURE_PROXY_SSL_HEADER", DJANGO_BEHIND_CLOUDFRONT="true")
    not_behind = load_settings("SECURE_PROXY_SSL_HEADER", DJANGO_BEHIND_CLOUDFRONT="false")

    assert behind["SECURE_PROXY_SSL_HEADER"] == ["HTTP_CLOUDFRONT_FORWARDED_PROTO", "https"]
    assert not_behind["SECURE_PROXY_SSL_HEADER"] is None


def test_passes_postgres_sslmode_to_the_connection():
    loaded = load_settings("DATABASES", POSTGRES_SSLMODE="require")

    assert loaded["DATABASES"]["default"]["OPTIONS"]["sslmode"] == "require"


def test_passes_the_deployment_checklist():
    result = run_in_new_process(
        ["manage.py", "check", "--deploy", "--fail-level", "WARNING"], **DEPLOYED_ENVIRONMENT
    )

    assert result.returncode == 0, result.stderr


def test_https_checks_stay_on_without_cloudfront():
    result = run_in_new_process(
        ["manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        **{**DEPLOYED_ENVIRONMENT, "DJANGO_BEHIND_CLOUDFRONT": "false"},
    )

    assert result.returncode != 0
    assert "security.W004" in result.stderr
    assert "security.W008" in result.stderr
