"""
GitHub Device Flow Authentication for Vecna.

Implements the OAuth device flow for GitHub authentication:
1. Request device code from GitHub
2. User visits URL and enters code
3. Poll for access token
4. Store token securely
"""

import asyncio
import aiohttp
from typing import Optional, Callable
from dataclasses import dataclass

from vecna.auth.storage import AuthStorage, TokenData, get_auth_storage


# GitHub OAuth endpoints
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"

# Vecna's GitHub OAuth App Client ID
VECNA_CLIENT_ID = "Ov23liACqal1HdkCFVnd"

# Required scopes for Copilot access
DEFAULT_SCOPE = "read:user"


@dataclass
class DeviceCodeResponse:
    """Response from GitHub device code request."""

    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


class AuthError(Exception):
    """Authentication error."""

    pass


class GitHubDeviceAuth:
    """
    GitHub OAuth device flow authentication.

    Usage:
        auth = GitHubDeviceAuth()

        # Start the flow
        device_info = await auth.request_device_code()
        print(f"Go to {device_info.verification_uri} and enter: {device_info.user_code}")

        # Poll for token (blocks until user authorizes or timeout)
        token = await auth.poll_for_token(device_info)
    """

    def __init__(
        self,
        client_id: str = VECNA_CLIENT_ID,
        scope: str = DEFAULT_SCOPE,
        storage: Optional[AuthStorage] = None,
    ):
        """
        Initialize GitHub device auth.

        Args:
            client_id: GitHub OAuth App client ID
            scope: OAuth scopes to request
            storage: Auth storage instance (uses global if not provided)
        """
        self.client_id = client_id
        self.scope = scope
        self.storage = storage or get_auth_storage()

    async def request_device_code(self) -> DeviceCodeResponse:
        """
        Request a device code from GitHub.

        Returns:
            DeviceCodeResponse with user code and verification URL

        Raises:
            AuthError: If the request fails
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(
                GITHUB_DEVICE_CODE_URL,
                data={
                    "client_id": self.client_id,
                    "scope": self.scope,
                },
                headers={
                    "Accept": "application/json",
                },
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    raise AuthError(f"Failed to get device code: {response.status} - {text}")

                data = await response.json()

                return DeviceCodeResponse(
                    device_code=data["device_code"],
                    user_code=data["user_code"],
                    verification_uri=data["verification_uri"],
                    expires_in=data["expires_in"],
                    interval=data["interval"],
                )

    async def poll_for_token(
        self,
        device_info: DeviceCodeResponse,
        on_pending: Optional[Callable[[], None]] = None,
    ) -> TokenData:
        """
        Poll GitHub for the access token after user authorization.

        Args:
            device_info: Response from request_device_code()
            on_pending: Optional callback called while waiting for user

        Returns:
            TokenData with access token

        Raises:
            AuthError: If authorization fails or times out
        """
        interval = device_info.interval
        deadline = asyncio.get_event_loop().time() + device_info.expires_in

        async with aiohttp.ClientSession() as session:
            while asyncio.get_event_loop().time() < deadline:
                async with session.post(
                    GITHUB_TOKEN_URL,
                    data={
                        "client_id": self.client_id,
                        "device_code": device_info.device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    headers={
                        "Accept": "application/json",
                    },
                ) as response:
                    data = await response.json()

                    # Check for success
                    if "access_token" in data:
                        token = TokenData(
                            access_token=data["access_token"],
                            refresh_token=data.get("refresh_token", ""),
                            token_type=data.get("token_type", "bearer"),
                            scope=data.get("scope", self.scope),
                        )

                        # Store the token
                        self.storage.set("github", token)

                        return token

                    # Handle errors
                    error = data.get("error")

                    if error == "authorization_pending":
                        # User hasn't authorized yet, keep waiting
                        if on_pending:
                            on_pending()
                        await asyncio.sleep(interval)
                        continue

                    elif error == "slow_down":
                        # GitHub wants us to slow down
                        interval += 5
                        await asyncio.sleep(interval)
                        continue

                    elif error == "expired_token":
                        raise AuthError("Device code expired. Please try again.")

                    elif error == "access_denied":
                        raise AuthError("Authorization denied by user.")

                    else:
                        error_desc = data.get("error_description", "Unknown error")
                        raise AuthError(f"Authorization failed: {error} - {error_desc}")

        raise AuthError("Authorization timed out. Please try again.")

    async def authenticate(
        self,
        on_code_received: Callable[[str, str], None],
        on_pending: Optional[Callable[[], None]] = None,
    ) -> TokenData:
        """
        Complete authentication flow.

        Args:
            on_code_received: Callback with (verification_uri, user_code)
            on_pending: Optional callback while waiting for user

        Returns:
            TokenData with access token
        """
        # Request device code
        device_info = await self.request_device_code()

        # Notify caller of the code
        on_code_received(device_info.verification_uri, device_info.user_code)

        # Poll for token
        return await self.poll_for_token(device_info, on_pending)

    def get_stored_token(self) -> Optional[TokenData]:
        """
        Get stored GitHub token if available.

        Returns:
            TokenData if found and valid, None otherwise
        """
        token = self.storage.get("github")
        if token and token.access_token and not token.is_expired():
            return token
        return None

    def is_authenticated(self) -> bool:
        """Check if we have a valid GitHub token."""
        return self.get_stored_token() is not None

    def logout(self) -> bool:
        """
        Remove stored GitHub token.

        Returns:
            True if token was removed, False if no token existed
        """
        return self.storage.delete("github")
