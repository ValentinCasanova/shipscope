"""The task's private IP addresses, from the ECS task metadata endpoint.

Load balancer health checks send the task's private IP as the Host header, so Django must
allow that IP, or it answers 400 and the load balancer marks the task unhealthy. ECS sets
ECS_CONTAINER_METADATA_URI_V4 in every container it runs; anywhere else, the lookup is
skipped.
"""

import json
import logging
import os
import urllib.request

logger = logging.getLogger(__name__)

METADATA_URI_VARIABLE = "ECS_CONTAINER_METADATA_URI_V4"
TIMEOUT_SECONDS = 1


def task_private_ips() -> list[str]:
    """Return the task's private IPv4 addresses, or an empty list outside ECS.

    This runs while the settings load, so a failure must not stop the app from starting.
    It logs a warning instead, and the load balancer's failing health checks lead there.
    """
    uri = os.environ.get(METADATA_URI_VARIABLE)
    if not uri:
        return []
    try:
        if not uri.startswith("http://"):
            raise ValueError(f"expected an http:// URL, got {uri!r}")
        # The scheme is checked above, so urlopen can't be pointed at a local file.
        with urllib.request.urlopen(uri, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            metadata = json.load(response)
        return [address for network in metadata["Networks"] for address in network["IPv4Addresses"]]
    except Exception as exc:  # Whatever went wrong, start without the task's IP.
        logger.warning(
            "Couldn't read the task's IP addresses from ECS task metadata, so load balancer "
            "health checks will fail: %s",
            exc,
        )
        return []
