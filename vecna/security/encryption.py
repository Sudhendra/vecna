"""Substrate encryption using Fernet (AES-128-CBC + HMAC-SHA256).

Provides encrypt/decrypt for substrate data at rest with two key sources:
- generate(): random key for ephemeral/session use
- from_password(): deterministic key from password + salt via PBKDF2
"""

import base64
import logging

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("vecna.security.encryption")


class SubstrateEncryption:
    """Encrypt/decrypt substrate data at rest using Fernet symmetric encryption."""

    def __init__(self, key: bytes):
        self._fernet = Fernet(key)

    @classmethod
    def generate(cls) -> "SubstrateEncryption":
        """Generate a new random encryption key."""
        return cls(Fernet.generate_key())

    @classmethod
    def from_password(cls, password: str, salt: bytes) -> "SubstrateEncryption":
        """Derive a deterministic key from a password using PBKDF2.

        Args:
            password: The user's password/passphrase.
            salt: A salt for the KDF (should be at least 16 bytes).

        Returns:
            A SubstrateEncryption instance with the derived key.
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480_000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return cls(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a plaintext string, returning a ciphertext string.

        Uses Fernet which includes a random IV, so encrypting the same
        plaintext twice produces different ciphertext.
        """
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt a ciphertext string, returning the original plaintext.

        Raises:
            cryptography.fernet.InvalidToken: If the ciphertext is invalid
                or was encrypted with a different key.
        """
        return self._fernet.decrypt(ciphertext.encode()).decode()
