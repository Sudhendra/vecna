"""
Auth Storage - Secure token persistence for Vecna.

Stores OAuth tokens in ~/.vecna/auth.json with chmod 0600 permissions.
"""

import os
import json
import stat
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class TokenData:
    """OAuth token data structure."""

    access_token: str = ""
    refresh_token: str = ""
    token_type: str = "bearer"
    scope: str = ""
    expires_at: Optional[float] = None  # Unix timestamp
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())

    def is_expired(self) -> bool:
        """Check if the token is expired."""
        if self.expires_at is None:
            return False
        return datetime.now().timestamp() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenData":
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class AuthStorage:
    """
    Secure storage for authentication tokens.

    Stores tokens in ~/.vecna/auth.json with restricted permissions (0600).
    """

    def __init__(self, storage_path: Optional[Path] = None):
        """
        Initialize auth storage.

        Args:
            storage_path: Optional custom path for auth.json
        """
        if storage_path is None:
            self.storage_dir = Path.home() / ".vecna"
            self.storage_path = self.storage_dir / "auth.json"
        else:
            self.storage_path = Path(storage_path)
            self.storage_dir = self.storage_path.parent

        self._ensure_storage_dir()
        self._data: Dict[str, TokenData] = {}
        self._load()

    def _ensure_storage_dir(self) -> None:
        """Ensure the storage directory exists with proper permissions."""
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        # Set directory permissions to 0700 (owner only)
        os.chmod(self.storage_dir, stat.S_IRWXU)

    def _secure_file(self) -> None:
        """Set file permissions to 0600 (owner read/write only)."""
        if self.storage_path.exists():
            os.chmod(self.storage_path, stat.S_IRUSR | stat.S_IWUSR)

    def _load(self) -> None:
        """Load tokens from storage file."""
        if not self.storage_path.exists():
            self._data = {}
            return

        try:
            with open(self.storage_path, "r") as f:
                raw_data = json.load(f)

            self._data = {}
            for provider, token_data in raw_data.items():
                if isinstance(token_data, dict):
                    self._data[provider] = TokenData.from_dict(token_data)
        except (json.JSONDecodeError, IOError) as e:
            # Start fresh if file is corrupted
            self._data = {}

    def _save(self) -> None:
        """Save tokens to storage file with secure permissions."""
        raw_data = {provider: token.to_dict() for provider, token in self._data.items()}

        # Write to temp file first, then rename (atomic write)
        temp_path = self.storage_path.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(raw_data, f, indent=2)

        # Set secure permissions before moving to final location
        os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)

        # Atomic rename
        temp_path.rename(self.storage_path)

    def get(self, provider: str) -> Optional[TokenData]:
        """
        Get token data for a provider.

        Args:
            provider: Provider name (e.g., "github_copilot")

        Returns:
            TokenData if found, None otherwise
        """
        return self._data.get(provider)

    def set(self, provider: str, token: TokenData) -> None:
        """
        Store token data for a provider.

        Args:
            provider: Provider name (e.g., "github_copilot")
            token: Token data to store
        """
        self._data[provider] = token
        self._save()

    def delete(self, provider: str) -> bool:
        """
        Delete token data for a provider.

        Args:
            provider: Provider name (e.g., "github_copilot")

        Returns:
            True if token was deleted, False if not found
        """
        if provider in self._data:
            del self._data[provider]
            self._save()
            return True
        return False

    def clear(self) -> None:
        """Clear all stored tokens."""
        self._data = {}
        if self.storage_path.exists():
            self.storage_path.unlink()

    def has_valid_token(self, provider: str) -> bool:
        """
        Check if a valid (non-expired) token exists for a provider.

        Args:
            provider: Provider name

        Returns:
            True if valid token exists
        """
        token = self.get(provider)
        if token is None:
            return False
        return bool(token.access_token) and not token.is_expired()

    def list_providers(self) -> list[str]:
        """
        List all providers with stored tokens.

        Returns:
            List of provider names
        """
        return list(self._data.keys())


# Singleton instance
_auth_storage: Optional[AuthStorage] = None


def get_auth_storage() -> AuthStorage:
    """Get the global auth storage instance."""
    global _auth_storage
    if _auth_storage is None:
        _auth_storage = AuthStorage()
    return _auth_storage
