"""A fake Google for tests: its signing keys, ID tokens, and token endpoint.

The `responses` library intercepts the requests session, so no test reaches Google.
Shared with the accounts tests.
"""

import time
from functools import cache
from typing import Any

import jwt
import responses
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from integrations.google import (
    JWKS_URI,
    REVOCATION_ENDPOINT,
    TOKEN_ENDPOINT,
    GoogleOAuthConfig,
)

CONFIG = GoogleOAuthConfig(
    client_id="test-client.apps.googleusercontent.com", client_secret="test-client-secret"
)
KEY_ID = "test-key"
SUB = "109876543210987654321"
NONCE = "test-nonce"
# Shaped like Google's tokens, so tests can search logs for them.
ACCESS_TOKEN = "ya29.test-access-token"
REFRESH_TOKEN = "1//test-refresh-token"


@cache
def signing_key(name: str = "google") -> rsa.RSAPrivateKey:
    """An RSA key, one per name, generated once per test run."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks(kid: str = KEY_ID) -> dict[str, Any]:
    """The key set Google publishes, holding the public half of signing_key()."""
    jwk = RSAAlgorithm.to_jwk(signing_key().public_key(), as_dict=True)
    return {"keys": [{**jwk, "kid": kid, "use": "sig", "alg": "RS256"}]}


def id_token(
    *,
    key: rsa.RSAPrivateKey | None = None,
    kid: str = KEY_ID,
    **claims: Any,
) -> str:
    """An ID token as Google issues it to CONFIG's client. Claims override the defaults;
    a claim set to None is left out."""
    now = int(time.time())
    payload = {
        "iss": "https://accounts.google.com",
        "azp": CONFIG.client_id,
        "aud": CONFIG.client_id,
        "sub": SUB,
        "email": "ada@example.com",
        "email_verified": True,
        "name": "Ada Lovelace",
        "given_name": "Ada",
        "family_name": "Lovelace",
        "nonce": NONCE,
        "iat": now,
        "exp": now + 3600,
        **claims,
    }
    payload = {name: value for name, value in payload.items() if value is not None}
    return jwt.encode(payload, key or signing_key(), algorithm="RS256", headers={"kid": kid})


def token_response(**fields: Any) -> dict[str, Any]:
    """The token endpoint's answer to a code exchange. Fields override the defaults."""
    body = {
        "access_token": ACCESS_TOKEN,
        "expires_in": 3599,
        "scope": "openid https://www.googleapis.com/auth/userinfo.email "
        "https://www.googleapis.com/auth/userinfo.profile",
        "token_type": "Bearer",
        "id_token": id_token(),
        **fields,
    }
    return {name: value for name, value in body.items() if value is not None}


def add_jwks(mock: responses.RequestsMock) -> None:
    mock.get(JWKS_URI, json=jwks())


def add_token(mock: responses.RequestsMock, **fields: Any) -> None:
    mock.post(TOKEN_ENDPOINT, json=token_response(**fields))


def add_token_error(mock: responses.RequestsMock, error: str, status: int = 400) -> None:
    mock.post(TOKEN_ENDPOINT, json={"error": error}, status=status)


def add_revoke(mock: responses.RequestsMock, status: int = 200) -> None:
    mock.post(REVOCATION_ENDPOINT, status=status)
