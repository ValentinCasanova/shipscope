import base64
from unittest import mock

import pytest
from django.db import InterfaceError, OperationalError, connection

HEALTH_URL = "/api/health/"


@pytest.mark.django_db
def test_reports_database_ok_when_query_succeeds(client):
    response = client.get(HEALTH_URL)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


# No django_db mark: this test simulates a database that can't be reached.
@pytest.mark.parametrize(
    "error",
    [
        pytest.param(OperationalError("connection refused"), id="OperationalError"),
        # Not a DatabaseError subclass, which is why the view catches db.Error.
        pytest.param(InterfaceError("the connection is closed"), id="InterfaceError"),
    ],
)
def test_reports_database_unavailable_when_query_fails(client, caplog, error):
    with mock.patch.object(connection, "cursor", side_effect=error):
        response = client.get(HEALTH_URL)

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "unavailable"}
    assert str(error) in caplog.text


@pytest.mark.django_db
@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="anonymous"),
        # DRF's default authentication classes would reject these credentials with a 403.
        pytest.param(
            {"Authorization": "Basic " + base64.b64encode(b"nobody:wrong").decode()},
            id="wrong-password",
        ),
    ],
)
def test_does_not_require_authentication(client, headers):
    response = client.get(HEALTH_URL, headers=headers)

    assert response.status_code == 200
