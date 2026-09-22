"""A stand-in for the ECS task metadata endpoint, for tests of config.ecs."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TASK_IP = "10.10.1.25"

# The parts of Fargate's container metadata response that the lookup reads.
CONTAINER_METADATA = {
    "Name": "api",
    "Networks": [
        {
            "NetworkMode": "awsvpc",
            "IPv4Addresses": [TASK_IP],
            "IPv4SubnetCIDRBlock": "10.10.1.0/24",
        },
    ],
}


class FakeMetadataEndpoint(ThreadingHTTPServer):
    """Stands in for the ECS task metadata endpoint. Tests change body and delay."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _MetadataHandler)
        self.body = json.dumps(CONTAINER_METADATA)
        self.delay = 0.0
        self.closing = threading.Event()


class _MetadataHandler(BaseHTTPRequestHandler):
    server: FakeMetadataEndpoint

    def do_GET(self) -> None:
        # Waiting on the event instead of sleeping lets the fixture end a slow response.
        self.server.closing.wait(self.server.delay)
        body = self.server.body.encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except OSError:
            pass  # The client stopped waiting, as the timeout test intends.

    def log_message(self, format: str, *args: object) -> None:
        pass  # Keep request lines out of the test output.
