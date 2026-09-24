import pytest

from accounts.tests.factories import UserFactory


@pytest.fixture
def superuser_client(client, db):
    """A test client signed in as a superuser.

    Faster than pytest-django's admin_client, which hashes a password for every test.
    """
    client.force_login(UserFactory(is_staff=True, is_superuser=True))
    return client
