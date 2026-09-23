import logging
from typing import Literal

from django import db
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    """Report that the API is running and whether the database answers a query.

    Responds 200 whenever the process is up, even while the database is down, so a load
    balancer doesn't replace healthy containers during a brief database outage.

    Open to everyone, with authentication skipped entirely: invalid or expired
    credentials can't get the request rejected, and no session or user lookup needs
    the database.
    """
    unused = "ruff should reject this"
    return Response({"status": "ok", "database": _database_status()})


def _database_status() -> Literal["ok", "unavailable"]:
    try:
        with db.connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except db.Error as exc:  # Every database error, including InterfaceError.
        logger.warning("Database health check failed: %s", exc)
        return "unavailable"
    return "ok"
