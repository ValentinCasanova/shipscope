"""Run Python in a new process, which loads the settings the way a container does."""

import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def environment_with(**variables: str | None) -> dict[str, str]:
    """This process's environment with the given changes. None removes a variable."""
    # Nothing in these tests connects to the database, but the settings require a
    # password.
    environment = {
        **os.environ,
        "DJANGO_SECRET_KEY": "test-secret-key",
        "POSTGRES_PASSWORD": "unused",
        **variables,
    }
    return {name: value for name, value in environment.items() if value is not None}


def run_in_new_process(
    args: list[str], **variables: str | None
) -> subprocess.CompletedProcess[str]:
    """Run python with these arguments in backend/ and return its exit code and output."""
    # The tests pass fixed arguments, never outside input.
    return subprocess.run(  # noqa: S603
        [sys.executable, *args],
        cwd=BACKEND_DIR,
        env=environment_with(**variables),
        capture_output=True,
        text=True,
        check=False,
    )
