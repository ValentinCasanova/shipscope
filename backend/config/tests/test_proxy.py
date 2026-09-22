"""Requests as they arrive in AWS: from CloudFront, and from load balancer health checks."""

import pytest
from django.test import Client

from .ecs_metadata import TASK_IP

CLOUDFRONT_HOST = "d111111abcdef8.cloudfront.net"

# CloudFront passes on the browser's Host header and adds the viewer's protocol.
FROM_CLOUDFRONT = {"Host": CLOUDFRONT_HOST, "CloudFront-Forwarded-Proto": "https"}


@pytest.fixture
def behind_cloudfront(settings):
    """What DJANGO_BEHIND_CLOUDFRONT=true sets (checked in test_settings.py)."""
    settings.ALLOWED_HOSTS = [CLOUDFRONT_HOST]
    settings.SECURE_PROXY_SSL_HEADER = ("HTTP_CLOUDFRONT_FORWARDED_PROTO", "https")


@pytest.fixture
def not_behind_cloudfront(settings):
    settings.ALLOWED_HOSTS = [CLOUDFRONT_HOST]
    settings.SECURE_PROXY_SSL_HEADER = None


def post_admin_login() -> int:
    """Submit the admin login form the way a browser on the CloudFront URL does, and
    return the response's status code."""
    client = Client(enforce_csrf_checks=True, headers=FROM_CLOUDFRONT)
    client.get("/admin/login/")  # Sets the CSRF cookie, as the browser's first visit does.
    response = client.post(
        "/admin/login/",
        {
            "username": "nobody",
            "password": "wrong",
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
        },
        headers={"Origin": f"https://{CLOUDFRONT_HOST}"},
    )
    return response.status_code


def test_request_is_secure_behind_cloudfront(rf, behind_cloudfront):
    request = rf.get("/api/health/", headers=FROM_CLOUDFRONT)

    assert request.is_secure()


def test_protocol_header_is_ignored_when_not_behind_cloudfront(rf, not_behind_cloudfront):
    request = rf.get("/api/health/", headers=FROM_CLOUDFRONT)

    assert not request.is_secure()


@pytest.mark.django_db
def test_csrf_accepts_the_https_origin_behind_cloudfront(behind_cloudfront, caplog):
    # 200 is the login form shown again for the wrong password: the CSRF check passed.
    assert post_admin_login() == 200
    assert "Forbidden" not in caplog.text


@pytest.mark.django_db
def test_csrf_rejects_the_https_origin_when_not_behind_cloudfront(not_behind_cloudfront, caplog):
    assert post_admin_login() == 403
    assert f"Origin checking failed - https://{CLOUDFRONT_HOST}" in caplog.text


@pytest.mark.django_db
def test_health_check_by_task_ip_is_allowed(settings):
    # Settings add the task's IP on ECS; the load balancer sends it with the port.
    settings.ALLOWED_HOSTS = [CLOUDFRONT_HOST, TASK_IP]

    response = Client().get("/api/health/", headers={"Host": f"{TASK_IP}:8000"})

    assert response.status_code == 200
