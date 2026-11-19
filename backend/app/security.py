"""Encryption of endpoint API keys at rest.

Keys are encrypted with Fernet (AES-128-CBC + HMAC-SHA256). The Fernet key is derived from
SECRET_KEY, so SECRET_KEY must be a long random value and must stay stable across restarts.
API keys are never returned by the API; responses only expose `has_api_key`.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class SecretDecryptionError(Exception):
    """Raised when a stored secret cannot be decrypted (usually because SECRET_KEY changed)."""


class SecretBox:
    def __init__(self, secret_key: str):
        derived_key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
        self._fernet = Fernet(derived_key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._fernet.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise SecretDecryptionError(
                "Stored API key could not be decrypted. SECRET_KEY may have changed; re-enter the key."
            ) from exc
