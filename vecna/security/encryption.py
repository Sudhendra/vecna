"""Substrate encryption using Fernet (AES-128-CBC + HMAC-SHA256).

Provides encrypt/decrypt for substrate data at rest with two key sources:
- generate(): random key for ephemeral/session use
- from_password(): deterministic key from password + salt via PBKDF2
- derive_key_from_password(): standalone key derivation function

Also provides JSON encrypt/decrypt for structured data (dicts).
"""

import base64
import json
import logging
import os
from typing import Any, Dict, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger("vecna.security.encryption")


def derive_key_from_password(
    password: str,
    salt: Optional[bytes] = None,
    iterations: int = 480_000,
) -> bytes:
    """Derive a Fernet-compatible key from a password.

    Uses PBKDF2-HMAC-SHA256 for key derivation.

    Args:
        password: The password string.
        salt: Salt bytes (16 bytes). Generated randomly if not provided.
        iterations: PBKDF2 iteration count.

    Returns:
        URL-safe base64-encoded Fernet key bytes (44 bytes).
    """
    if salt is None:
        salt = os.urandom(16)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))


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
        key = derive_key_from_password(password, salt=salt)
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

    def encrypt_json(self, data: Dict[str, Any]) -> bytes:
        """Encrypt a dictionary as JSON bytes.

        Serializes the dict to JSON, then encrypts the resulting bytes
        using Fernet symmetric encryption.

        Args:
            data: Dictionary to encrypt.

        Returns:
            Encrypted bytes (Fernet token).
        """
        plaintext = json.dumps(data).encode("utf-8")
        return self._fernet.encrypt(plaintext)

    def decrypt_json(self, encrypted: bytes) -> Dict[str, Any]:
        """Decrypt bytes back to a dictionary.

        Args:
            encrypted: Encrypted bytes from encrypt_json.

        Returns:
            Decrypted dictionary.

        Raises:
            cryptography.fernet.InvalidToken: If the key is wrong or
                the data is corrupted.
        """
        plaintext = self._fernet.decrypt(encrypted)
        result: Dict[str, Any] = json.loads(plaintext.decode("utf-8"))
        return result
