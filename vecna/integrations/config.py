"""
Integration configuration and registry.

Manages which integrations are available, which are enabled,
and credential validation for each integration.
"""

import logging
from typing import Any, Dict, List, Set, Type

from vecna.integrations.base import BaseIntegration

logger = logging.getLogger("vecna.integrations.config")


class IntegrationRegistry:
    """Registry of available integrations."""

    def __init__(self) -> None:
        self._integrations: Dict[str, Type[BaseIntegration]] = {}

    def register(self, integration_cls: Type[BaseIntegration]) -> None:
        """Register an integration class by its name attribute."""
        self._integrations[integration_cls.name] = integration_cls

    def list_available(self) -> List[str]:
        """List all registered integration names."""
        return list(self._integrations.keys())

    def get(self, name: str) -> Type[BaseIntegration]:
        """
        Get an integration class by name.

        Raises:
            KeyError: If no integration with the given name is registered.
        """
        if name not in self._integrations:
            raise KeyError(f"Integration not found: {name}")
        return self._integrations[name]


class IntegrationConfig:
    """
    Configuration for which integrations are enabled.

    Manages enable/disable toggles and credential storage.
    Credentials are never included in serialized output for security.
    """

    def __init__(self) -> None:
        self._enabled: Set[str] = set()
        self._credentials: Dict[str, Dict[str, str]] = {}

    def enable(self, name: str) -> None:
        """Enable an integration by name."""
        self._enabled.add(name)

    def disable(self, name: str) -> None:
        """Disable an integration by name. No-op if already disabled."""
        self._enabled.discard(name)

    def is_enabled(self, name: str) -> bool:
        """Check if an integration is enabled."""
        return name in self._enabled

    def list_enabled(self) -> List[str]:
        """List all currently enabled integration names."""
        return list(self._enabled)

    def set_credentials(self, name: str, creds: Dict[str, str]) -> None:
        """Store credentials for an integration."""
        self._credentials[name] = creds

    def get_credentials(self, name: str) -> Dict[str, str]:
        """Get credentials for an integration. Returns empty dict if none set."""
        return self._credentials.get(name, {})

    def validate_credentials(self, name: str, registry: IntegrationRegistry) -> List[str]:
        """
        Validate that all required credentials are present for an integration.

        Args:
            name: The integration name to validate credentials for.
            registry: The registry to look up required credentials from.

        Returns:
            List of missing credential key names. Empty list means all present.

        Raises:
            KeyError: If the integration is not registered in the registry.
        """
        integration_cls = registry.get(name)
        required = integration_cls.required_credentials
        provided = self.get_credentials(name)
        return [key for key in required if key not in provided]

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize config to dict.

        Credentials are never serialized for security.
        """
        return {
            "enabled": sorted(self._enabled),
            "credentials": {},  # Never serialize credentials
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntegrationConfig":
        """Restore config from a serialized dict."""
        config = cls()
        for name in data.get("enabled", []):
            config.enable(name)
        return config
