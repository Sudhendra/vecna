"""Privacy tier system for controlling what data leaves the local machine.

Three tiers:
- LOCAL_ONLY: Never leaves the machine (SSNs, passwords, local secrets)
- PROCESSABLE: Can be sent to cloud LLMs for processing (preferences, context)
- SHAREABLE: Can be shared externally (public knowledge, general facts)
"""

import logging
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger("vecna.security.privacy")


class PrivacyTier(Enum):
    """Privacy classification for data items."""

    LOCAL_ONLY = "local_only"
    PROCESSABLE = "processable"
    SHAREABLE = "shareable"

    def can_send_to_cloud(self) -> bool:
        """Return True if this tier permits sending data to cloud services."""
        return self in (PrivacyTier.PROCESSABLE, PrivacyTier.SHAREABLE)


class PrivacyFilter:
    """Filter data based on privacy tiers before sending to cloud models."""

    def filter_for_cloud(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove LOCAL_ONLY items before sending to cloud.

        Items without a privacy_tier or with an unrecognized tier value
        are treated as shareable (allowed through). Only items explicitly
        marked as 'local_only' are filtered out.

        Args:
            items: List of dicts, each optionally containing a 'privacy_tier' key.

        Returns:
            A new list containing only items that may be sent to cloud services.
        """
        return [item for item in items if item.get("privacy_tier") != PrivacyTier.LOCAL_ONLY.value]
