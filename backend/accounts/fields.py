"""A model field that stores text encrypted, for users' Google tokens (4.1.2).

A Google refresh token lets whoever holds it open the user's files that ShipScope can
open, for months. Encrypted by the app, the tokens are only ciphertext in the database,
its backups, and any dump of it. Reading one also takes the key, which only the running
app has: ECS hands it the TOKEN_ENCRYPTION_KEY secret when a task starts.

Fernet, from the cryptography package, encrypts with AES-128 in CBC mode and signs the
result with HMAC-SHA256. A value that was altered, or encrypted with another key, is
refused instead of being decrypted into garbage.
"""

import base64
import functools
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.core.exceptions import FieldError, ImproperlyConfigured
from django.db import models
from django.db.models import lookups

logger = logging.getLogger(__name__)

# What the derived key is for. Another purpose would derive another key from the same
# secret, and neither key would reveal the other.
KEY_PURPOSE = b"shipscope accounts.EncryptedTextField"


def encryption_configured() -> bool:
    """Whether TOKEN_ENCRYPTION_KEY is set, which storing a non-empty value needs."""
    return bool(settings.TOKEN_ENCRYPTION_KEY)


def encrypt(plaintext: str) -> str:
    """The plaintext encrypted, as Fernet's URL-safe text, which starts with gAAAAA."""
    return _fernet().encrypt(plaintext.encode()).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """The plaintext of encrypt()'s result.

    Raises InvalidToken if the ciphertext was altered, or encrypted with another key.
    """
    return _fernet().decrypt(ciphertext).decode()


def _fernet() -> Fernet:
    secret = settings.TOKEN_ENCRYPTION_KEY
    if not secret:
        raise ImproperlyConfigured(
            "TOKEN_ENCRYPTION_KEY is empty, so Google tokens can't be encrypted or decrypted"
        )
    return _fernet_for(secret)


@functools.cache
def _fernet_for(secret: str) -> Fernet:
    """Fernet with the key that HKDF-SHA256 derives from the secret.

    Fernet takes exactly 32 random bytes, and the secret is text of any length, such as
    the 64 random letters and digits that Terraform generates. HKDF turns it into 32
    bytes as unpredictable as the secret itself. It needs no salt, because the secret is
    already random. Cached per secret, so a changed setting gets its own key.
    """
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=KEY_PURPOSE).derive(
        secret.encode()
    )
    return Fernet(base64.urlsafe_b64encode(key))


class EncryptedTextField(models.TextField):
    """Text that the database holds encrypted with Fernet, under TOKEN_ENCRYPTION_KEY.

    Code reads and writes plain text: a value is encrypted on its way to the database,
    and decrypted when it's loaded.

    - An empty value is stored as it is. It needs no key, and whether a value is empty
      can be queried: filter(field="") works. Every other lookup raises FieldError,
      since encrypting the same text twice gives two different ciphertexts.
    - Without a key, saving or loading a non-empty value raises ImproperlyConfigured.
    - A stored value that can't be decrypted, because it was encrypted with another key
      or altered, loads as empty, with a warning (G61). Failing instead would make the
      whole row unreadable, and with it signing in. Code then treats the value as a
      token it doesn't have: the user connects Google Drive again.
    """

    def from_db_value(self, value: str | None, expression: Any, connection: Any) -> str | None:
        if not value:
            return value
        try:
            return decrypt(value)
        except InvalidToken:
            logger.warning(
                "%s.%s can't be decrypted: it was encrypted with another key, or altered. "
                "It loads as empty.",
                self.model._meta.label,
                self.name,
            )
            return ""

    def get_prep_value(self, value: Any) -> Any:
        value = super().get_prep_value(value)
        return encrypt(value) if value else value

    def get_lookup(self, lookup_name: str) -> type[lookups.Lookup] | None:
        return _IsEmpty if lookup_name == "exact" else None


class _IsEmpty(lookups.Exact):
    """An encrypted field's only lookup: whether its value is empty."""

    def get_prep_lookup(self) -> Any:
        if self.rhs != "":
            raise FieldError("An encrypted field can only be compared with an empty string")
        return super().get_prep_lookup()
