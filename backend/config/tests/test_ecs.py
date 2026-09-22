import json
import time
from unittest import mock

import pytest

from config import ecs

from .ecs_metadata import TASK_IP


def test_returns_the_task_ip_addresses(metadata_endpoint):
    assert ecs.task_private_ips() == [TASK_IP]


def test_skips_the_lookup_outside_ecs(monkeypatch):
    monkeypatch.delenv("ECS_CONTAINER_METADATA_URI_V4", raising=False)

    with mock.patch("urllib.request.urlopen") as urlopen:
        assert ecs.task_private_ips() == []

    urlopen.assert_not_called()


def test_gives_up_after_the_timeout(metadata_endpoint, caplog):
    metadata_endpoint.delay = ecs.TIMEOUT_SECONDS + 5

    started = time.monotonic()
    addresses = ecs.task_private_ips()

    assert addresses == []
    assert time.monotonic() - started < ecs.TIMEOUT_SECONDS + 1
    assert "Couldn't read the task's IP addresses" in caplog.text


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("<html>not JSON</html>", id="not-json"),
        pytest.param(json.dumps({"Name": "api"}), id="no-networks"),
        pytest.param(json.dumps(["unexpected"]), id="wrong-shape"),
    ],
)
def test_returns_nothing_for_a_malformed_response(metadata_endpoint, caplog, body):
    metadata_endpoint.body = body

    assert ecs.task_private_ips() == []
    assert "Couldn't read the task's IP addresses" in caplog.text


def test_refuses_urls_that_are_not_http(monkeypatch, caplog):
    monkeypatch.setenv("ECS_CONTAINER_METADATA_URI_V4", "file:///etc/hostname")

    assert ecs.task_private_ips() == []
    assert "expected an http:// URL" in caplog.text
