"""Encrypted file-based state persistence.

Provides save/load operations for HiveState with Fernet
encryption at rest. State is serialized to JSON, encrypted,
and written to a file. On load, the file is decrypted and
deserialized back to HiveState.
"""

import hashlib
import logging
import os

from vecna.core.hive_state import HiveState
from vecna.security.encryption import SubstrateEncryption

logger = logging.getLogger("vecna.core.encrypted_state_store")


class EncryptedStateStore:
    """Encrypted file-based HiveState persistence.

    Uses SubstrateEncryption (Fernet) to encrypt state before
    writing to disk and decrypt on loading.

    The encryption key is derived deterministically from the password
    using PBKDF2 with a salt derived from the password itself,
    ensuring the same password always produces the same key.
    """

    def __init__(
        self,
        filepath: str,
        password: str,
    ) -> None:
        """Initialize the encrypted store.

        Args:
            filepath: Path to the encrypted state file.
            password: Encryption password.
        """
        self._filepath = filepath
        # Derive a deterministic salt from the password so the same
        # password always yields the same key across restarts.
        salt = hashlib.sha256(password.encode()).digest()[:16]
        self._encryption = SubstrateEncryption.from_password(password, salt=salt)

    def save(self, state: HiveState) -> None:
        """Save HiveState encrypted to file.

        Serializes state to dict, encrypts, and writes to disk.

        Args:
            state: The HiveState to persist.
        """
        state_dict = state.to_full_dict()
        encrypted = self._encryption.encrypt_json(state_dict)

        parent_dir = os.path.dirname(self._filepath)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        with open(self._filepath, "wb") as f:
            f.write(encrypted)

        logger.info(
            "State saved (encrypted) to %s (%d bytes)",
            self._filepath,
            len(encrypted),
        )

    def load(self) -> HiveState:
        """Load HiveState from encrypted file.

        If the file doesn't exist, returns a fresh HiveState.

        Returns:
            Decrypted HiveState.

        Raises:
            cryptography.fernet.InvalidToken: If the password is wrong
                or the file is corrupted.
        """
        if not os.path.exists(self._filepath):
            logger.info(
                "No state file at %s, returning empty state",
                self._filepath,
            )
            return HiveState()

        with open(self._filepath, "rb") as f:
            encrypted = f.read()

        # Let InvalidToken propagate for wrong password / corrupted file
        state_dict = self._encryption.decrypt_json(encrypted)
        state = HiveState.from_dict(state_dict)
        logger.info(
            "State loaded (decrypted) from %s",
            self._filepath,
        )
        return state
