import threading

import pytest

from .ecs_metadata import FakeMetadataEndpoint


@pytest.fixture
def metadata_endpoint(monkeypatch):
    """Run a fake metadata endpoint and point ECS_CONTAINER_METADATA_URI_V4 at it."""
    server = FakeMetadataEndpoint()
    # A short poll interval makes shutdown() return quickly.
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    monkeypatch.setenv(
        "ECS_CONTAINER_METADATA_URI_V4", f"http://127.0.0.1:{server.server_port}/v4/abc123"
    )
    yield server
    server.closing.set()
    server.shutdown()
    server.server_close()
