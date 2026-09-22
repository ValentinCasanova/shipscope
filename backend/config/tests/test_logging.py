import json
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

from .processes import BACKEND_DIR, environment_with, run_in_new_process

# Logs a warning, and an error with a traceback, after Django configures logging.
LOGGING_SCRIPT = """
import logging
import django

django.setup()
log = logging.getLogger("shipscope.test")
log.warning("Something %s happened", "odd")
try:
    1 / 0
except ZeroDivisionError:
    log.exception("It failed")
"""


def run_logging_script(log_format: str | None) -> subprocess.CompletedProcess[str]:
    return run_in_new_process(
        ["-c", LOGGING_SCRIPT],
        DJANGO_SETTINGS_MODULE="config.settings",
        DJANGO_LOG_FORMAT=log_format,
    )


def test_json_format_writes_one_object_per_record():
    result = run_logging_script("json")

    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert [(r["level"], r["logger"], r["message"]) for r in records] == [
        ("WARNING", "shipscope.test", "Something odd happened"),
        ("ERROR", "shipscope.test", "It failed"),
    ]
    assert "ZeroDivisionError" in records[1]["exc_info"]
    assert all(re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", r["time"]) for r in records)


def test_plain_format_is_the_default():
    result = run_logging_script(None)

    assert result.returncode == 0, result.stderr
    first_line = result.stdout.splitlines()[0]
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} WARNING shipscope.test Something odd happened",
        first_line,
    )


def test_rejects_an_unknown_log_format():
    result = run_in_new_process(["manage.py", "check"], DJANGO_LOG_FORMAT="xml")

    assert result.returncode != 0
    assert "DJANGO_LOG_FORMAT must be one of plain, json, not 'xml'" in result.stderr


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until_listening(server: subprocess.Popen[str], port: int) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        assert server.poll() is None, "Gunicorn exited during startup"
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            return
        except OSError:
            time.sleep(0.1)
    raise AssertionError("Gunicorn didn't start listening within 20 seconds")


def http_status(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # noqa: S310 (a local URL)
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_gunicorn_and_django_write_each_record_once_as_json():
    port = free_port()
    # The Dockerfile's command, on a local port. Gunicorn loads gunicorn.conf.py from
    # the working directory, as it does in the image.
    command = [
        sys.executable,
        "-m",
        "gunicorn",
        "config.wsgi",
        "--bind",
        f"127.0.0.1:{port}",
        "--access-logfile",
        "-",
        "--worker-tmp-dir",
        "/dev/shm",  # noqa: S108 (worker heartbeat files, as in the Dockerfile)
        "--no-control-socket",
    ]
    environment = environment_with(
        DJANGO_LOG_FORMAT="json",
        DJANGO_DEBUG="false",
        DJANGO_ALLOWED_HOSTS="127.0.0.1",
        WEB_CONCURRENCY="2",
    )
    # The tests pass fixed arguments, never outside input.
    server = subprocess.Popen(  # noqa: S603
        command,
        cwd=BACKEND_DIR,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        wait_until_listening(server, port)
        # Django logs a warning for a 404, without touching the database.
        status = http_status(f"http://127.0.0.1:{port}/api/does-not-exist/")
    finally:
        server.terminate()
        stdout, stderr = server.communicate(timeout=30)

    assert status == 404
    records = [json.loads(line) for line in (stdout + stderr).splitlines()]
    access = [r for r in records if r["logger"] == "gunicorn.access"]
    not_found = [r for r in records if r["message"] == "Not Found: /api/does-not-exist/"]
    assert len(access) == 1
    assert '"GET /api/does-not-exist/ HTTP/1.1" 404' in access[0]["message"]
    assert [(r["level"], r["logger"]) for r in not_found] == [("WARNING", "django.request")]
    assert any(
        r["logger"] == "gunicorn.error" and f"Listening at: http://127.0.0.1:{port}" in r["message"]
        for r in records
    )
