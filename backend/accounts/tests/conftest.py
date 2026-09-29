import pytest
import responses

from accounts import services
from integrations.tests.fake_google import CONFIG


@pytest.fixture(autouse=True)
def google_settings(settings):
    """The fake Google client's settings, in place of any from the local .env."""
    settings.GOOGLE_OAUTH_CLIENT_ID = CONFIG.client_id
    settings.GOOGLE_OAUTH_CLIENT_SECRET = CONFIG.client_secret
    # The cached client keeps Google's keys, which each test fakes anew.
    services._client_for.cache_clear()
    yield settings
    services._client_for.cache_clear()


@pytest.fixture
def google():
    """Fakes Google's endpoints. A request to any URL a test didn't add fails the test."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock
