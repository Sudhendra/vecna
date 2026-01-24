"""
GitHub Copilot Authentication and API Access for Vecna.

Handles:
1. Exchanging GitHub token for Copilot token
2. Discovering available models
3. Providing authenticated access to Copilot API
4. System-level token discovery (keychain, config files)
"""

import asyncio
import aiohttp
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime

from vecna.auth.storage import AuthStorage, TokenData, get_auth_storage
from vecna.auth.github import GitHubDeviceAuth
from vecna.auth.system import SystemTokenDiscovery, DiscoveredToken, discover_github_token


# Copilot API endpoints
COPILOT_API_BASE = "https://api.githubcopilot.com"
COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
COPILOT_MODELS_URL = f"{COPILOT_API_BASE}/models"

# User agent for Copilot API
VECNA_USER_AGENT = "vecna/0.1.0"


@dataclass
class CopilotModel:
    """Information about an available Copilot model."""

    id: str
    name: str
    version: str = ""
    vendor: str = ""
    family: str = ""
    max_input_tokens: int = 0
    max_output_tokens: int = 0
    capabilities: List[str] = field(default_factory=list)
    is_default: bool = False

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "CopilotModel":
        """Create from Copilot API response."""
        return cls(
            id=data.get("id", ""),
            name=data.get("name", data.get("id", "")),
            version=data.get("version", ""),
            vendor=data.get("vendor", ""),
            family=data.get("family", ""),
            max_input_tokens=data.get("capabilities", {})
            .get("limits", {})
            .get("max_prompt_tokens", 0),
            max_output_tokens=data.get("capabilities", {})
            .get("limits", {})
            .get("max_output_tokens", 0),
            capabilities=data.get("capabilities", {}).get("type", "chat").split(","),
            is_default=data.get("is_default", False),
        )


class CopilotAuthError(Exception):
    """Copilot authentication error."""

    pass


class CopilotAuth:
    """
    GitHub Copilot authentication and API access.

    Handles token exchange and model discovery with multiple token sources:
    1. Stored tokens from OAuth device flow
    2. System tokens (macOS Keychain, config files, env vars)

    Usage:
        copilot = CopilotAuth()

        # Check if authenticated (tries system tokens too)
        if not copilot.is_authenticated():
            # Need to do GitHub auth first
            github_auth = GitHubDeviceAuth()
            await github_auth.authenticate(...)

        # Get Copilot token
        token = await copilot.get_copilot_token()

        # Discover models
        models = await copilot.discover_models()
    """

    def __init__(self, storage: Optional[AuthStorage] = None):
        """
        Initialize Copilot auth.

        Args:
            storage: Auth storage instance (uses global if not provided)
        """
        self.storage = storage or get_auth_storage()
        self._github_auth = GitHubDeviceAuth(storage=self.storage)
        self._system_discovery = SystemTokenDiscovery()
        self._system_token: Optional[DiscoveredToken] = None

    def is_github_authenticated(self) -> bool:
        """Check if we have a valid GitHub token (stored or system)."""
        # Check stored token first
        if self._github_auth.is_authenticated():
            return True
        # Try system token discovery
        system_token = self._system_discovery.discover()
        if system_token:
            self._system_token = system_token
            return True
        return False

    def is_authenticated(self) -> bool:
        """Check if we have a valid Copilot token or can get one."""
        token = self.storage.get("copilot")
        if token and token.access_token and not token.is_expired():
            return True
        # Fall back to GitHub token (we can exchange it)
        return self.is_github_authenticated()

    def get_token_source(self) -> Optional[str]:
        """
        Get a description of where the current token came from.

        Returns:
            Description string or None if not authenticated
        """
        # Check stored token first
        if self._github_auth.is_authenticated():
            return "VECNA OAuth device flow"

        # Check system token
        system_token = self._system_discovery.discover()
        if system_token:
            return system_token.source

        return None

    def _get_github_token(self) -> Optional[str]:
        """
        Get GitHub token from any available source.

        Priority:
        1. Stored token from OAuth device flow
        2. System token (keychain, config, env)

        Returns:
            GitHub OAuth token or None
        """
        # Try stored token first
        stored = self._github_auth.get_stored_token()
        if stored and stored.access_token:
            return stored.access_token

        # Try system discovery
        system_token = self._system_discovery.discover()
        if system_token:
            self._system_token = system_token
            return system_token.token

        return None

    async def get_copilot_token(self, force_refresh: bool = False) -> TokenData:
        """
        Get a Copilot access token.

        This exchanges the GitHub token for a Copilot-specific token.
        Tries multiple token sources: stored OAuth, system keychain, env vars.

        Args:
            force_refresh: Force refresh even if cached token is valid

        Returns:
            TokenData with Copilot access token

        Raises:
            CopilotAuthError: If token exchange fails
        """
        # Check for cached Copilot token
        if not force_refresh:
            cached = self.storage.get("copilot")
            if cached and cached.access_token and not cached.is_expired():
                return cached

        # Get GitHub token from any source
        github_token = self._get_github_token()
        if not github_token:
            raise CopilotAuthError(
                "No GitHub token available. Please authenticate with 'vecna auth login' "
                "or ensure you have VS Code Copilot configured."
            )

        # Exchange for Copilot token
        return await self._exchange_token(github_token)

    async def _exchange_token(self, github_token: str) -> TokenData:
        """
        Exchange a GitHub token for a Copilot API token.

        Args:
            github_token: GitHub OAuth token

        Returns:
            TokenData with Copilot access token

        Raises:
            CopilotAuthError: If exchange fails
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(
                COPILOT_TOKEN_URL,
                headers={
                    "Authorization": f"Token {github_token}",
                    "Accept": "application/json",
                    "User-Agent": VECNA_USER_AGENT,
                },
            ) as response:
                if response.status == 401:
                    raise CopilotAuthError(
                        "GitHub token is invalid or expired. Please re-authenticate."
                    )

                if response.status == 403:
                    raise CopilotAuthError(
                        "Access denied. Make sure you have an active GitHub Copilot subscription."
                    )

                if response.status != 200:
                    text = await response.text()
                    raise CopilotAuthError(
                        f"Failed to get Copilot token: {response.status} - {text}"
                    )

                data = await response.json()

                # Parse expiration - Copilot returns Unix timestamp
                expires_at = None
                if "expires_at" in data:
                    try:
                        # It's a Unix timestamp
                        expires_at = float(data["expires_at"])
                    except (ValueError, TypeError):
                        try:
                            # Maybe ISO format
                            exp_dt = datetime.fromisoformat(
                                str(data["expires_at"]).replace("Z", "+00:00")
                            )
                            expires_at = exp_dt.timestamp()
                        except (ValueError, TypeError):
                            pass

                token = TokenData(
                    access_token=data.get("token", ""),
                    token_type="bearer",
                    expires_at=expires_at,
                )

                # Store additional Copilot info
                self._copilot_info = {
                    "endpoints": data.get("endpoints", {}),
                    "chat_enabled": data.get("chat_enabled", False),
                    "individual": data.get("individual", False),
                    "sku": data.get("sku", ""),
                }

                # Cache the token
                self.storage.set("copilot", token)

                return token

    async def discover_models(self) -> List[CopilotModel]:
        """
        Discover available models from GitHub Copilot.

        Returns:
            List of available CopilotModel objects

        Raises:
            CopilotAuthError: If discovery fails
        """
        token = await self.get_copilot_token()

        # Headers required by the Copilot API
        headers = {
            "Authorization": f"Bearer {token.access_token}",
            "User-Agent": VECNA_USER_AGENT,
            "Accept": "application/json",
            "Editor-Version": "vscode/1.96.0",
            "Editor-Plugin-Version": "copilot-chat/0.25.0",
            "Copilot-Integration-Id": "vscode-chat",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(
                COPILOT_MODELS_URL,
                headers=headers,
            ) as response:
                if response.status == 401:
                    # Token might have expired, try refreshing
                    token = await self.get_copilot_token(force_refresh=True)
                    headers["Authorization"] = f"Bearer {token.access_token}"
                    async with session.get(
                        COPILOT_MODELS_URL,
                        headers=headers,
                    ) as retry_response:
                        if retry_response.status != 200:
                            text = await retry_response.text()
                            raise CopilotAuthError(
                                f"Failed to discover models: {retry_response.status} - {text}"
                            )
                        data = await retry_response.json()
                else:
                    if response.status != 200:
                        text = await response.text()
                        raise CopilotAuthError(
                            f"Failed to discover models: {response.status} - {text}"
                        )
                    data = await response.json()

        # Parse models
        models = []
        model_list = data.get("models", data.get("data", []))

        if isinstance(model_list, list):
            for model_data in model_list:
                if isinstance(model_data, dict):
                    models.append(CopilotModel.from_api_response(model_data))

        return models

    def get_api_headers(self, token: TokenData) -> Dict[str, str]:
        """
        Get headers for Copilot API requests.

        Args:
            token: Copilot access token

        Returns:
            Headers dict for API requests
        """
        return {
            "Authorization": f"Bearer {token.access_token}",
            "User-Agent": VECNA_USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Openai-Intent": "conversation-panel",
            "Editor-Version": "vscode/1.85.0",
            "Editor-Plugin-Version": "copilot-chat/0.12.0",
        }

    def logout(self) -> None:
        """Remove all stored tokens (GitHub and Copilot)."""
        self.storage.delete("github")
        self.storage.delete("copilot")


# Singleton instance
_copilot_auth: Optional[CopilotAuth] = None


def get_copilot_auth() -> CopilotAuth:
    """Get the global Copilot auth instance."""
    global _copilot_auth
    if _copilot_auth is None:
        _copilot_auth = CopilotAuth()
    return _copilot_auth
