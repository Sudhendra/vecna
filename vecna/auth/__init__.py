"""
Vecna Auth Module - GitHub Copilot Authentication

Provides OAuth device flow authentication and system token discovery
for GitHub Copilot access.

Token sources (in priority order):
1. Stored tokens from VECNA OAuth device flow
2. macOS Keychain (VS Code Copilot auth)
3. GitHub Copilot config files (hosts.json, apps.json)
4. GITHUB_TOKEN environment variable
5. gh CLI configuration
"""

from vecna.auth.storage import AuthStorage, TokenData
from vecna.auth.github import GitHubDeviceAuth
from vecna.auth.copilot import CopilotAuth, CopilotModel
from vecna.auth.system import SystemTokenDiscovery, DiscoveredToken, discover_github_token

__all__ = [
    "AuthStorage",
    "TokenData",
    "GitHubDeviceAuth",
    "CopilotAuth",
    "CopilotModel",
    "SystemTokenDiscovery",
    "DiscoveredToken",
    "discover_github_token",
]
