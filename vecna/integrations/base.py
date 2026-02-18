"""
Base integration class.

Every integration (Google Suite, GitHub, Slack, etc.) implements this ABC.
Inspired by Home Assistant's integration architecture.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger("vecna.integrations")


@dataclass
class IntegrationStatus:
    """Health status of an integration."""

    healthy: bool
    name: str
    message: str = ""
    last_checked: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseIntegration(ABC):
    """
    Abstract base class for all Vecna integrations.

    Subclasses must define class-level attributes:
        name: str — unique identifier for this integration
        description: str — human-readable description
        required_credentials: List[str] — credential keys needed to operate

    And implement the abstract methods: check_health(), start(), stop().
    """

    name: str = "unnamed"
    description: str = ""
    required_credentials: List[str] = []
    enabled: bool = False

    @abstractmethod
    async def check_health(self) -> IntegrationStatus:
        """Check if the integration is healthy and connected."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start the integration (connect, authenticate, begin polling)."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the integration gracefully."""
        ...

    def get_credential_keys(self) -> List[str]:
        """Return the credential keys this integration needs."""
        return self.required_credentials
