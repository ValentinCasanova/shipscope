import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def run_manage_py_check(secret_key: str) -> subprocess.CompletedProcess[str]:
    """Load the settings in a new process, the way a container loads them at startup."""
    # check doesn't connect to the database, but the settings require a password.
    env = {**os.environ, "DJANGO_SECRET_KEY": secret_key, "POSTGRES_PASSWORD": "unused"}
    return subprocess.run(
        [sys.executable, "manage.py", "check"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_starts_with_a_secret_key():
    result = run_manage_py_check("test-secret-key")

    assert result.returncode == 0, result.stderr


def test_fails_at_startup_when_secret_key_is_empty():
    result = run_manage_py_check("")

    assert result.returncode != 0
    assert "The DJANGO_SECRET_KEY environment variable is empty" in result.stderr
