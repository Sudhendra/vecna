"""
System-level GitHub token discovery for Vecna.

Discovers GitHub tokens from system sources:
1. macOS Keychain (for VS Code/Copilot)
2. GitHub Copilot config files (hosts.json, apps.json)
3. Environment variables (GITHUB_TOKEN)
4. gh CLI configuration

This allows VECNA to use existing Copilot authentication
without requiring a separate OAuth flow.
"""

import os
import json
import subprocess
import platform
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class DiscoveredToken:
    """A token discovered from system sources."""

    token: str
    source: str  # Description of where it was found
    account: Optional[str] = None  # Associated account/user if known


class SystemTokenDiscovery:
    """
    Discovers GitHub tokens from system sources.

    Priority order:
    1. Environment variable GITHUB_TOKEN
    2. macOS Keychain (VS Code Copilot auth)
    3. GitHub Copilot config files
    4. gh CLI configuration
    """

    def __init__(self):
        self._system = platform.system()

    def discover(self) -> Optional[DiscoveredToken]:
        """
        Discover a GitHub token from system sources.

        Returns:
            DiscoveredToken if found, None otherwise
        """
        # Try sources in priority order
        methods = [
            self._from_environment,
            self._from_macos_keychain,
            self._from_copilot_config,
            self._from_gh_cli,
        ]

        for method in methods:
            try:
                result = method()
                if result and result.token:
                    return result
            except Exception:
                # Continue to next source on any error
                continue

        return None

    def discover_all(self) -> list[DiscoveredToken]:
        """
        Discover all available GitHub tokens from system sources.

        Returns:
            List of all discovered tokens
        """
        tokens = []
        methods = [
            self._from_environment,
            self._from_macos_keychain,
            self._from_copilot_config,
            self._from_gh_cli,
        ]

        for method in methods:
            try:
                result = method()
                if result and result.token:
                    tokens.append(result)
            except Exception:
                continue

        return tokens

    def _from_environment(self) -> Optional[DiscoveredToken]:
        """Check GITHUB_TOKEN environment variable."""
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            return DiscoveredToken(token=token, source="Environment variable GITHUB_TOKEN")
        return None

    def _from_macos_keychain(self) -> Optional[DiscoveredToken]:
        """
        Read GitHub token from macOS Keychain.

        VS Code stores the GitHub OAuth token as an internet password
        for github.com in the login keychain.

        Note: This requires user authorization (Touch ID / password) on first access.
        The keychain may cache authorization for subsequent accesses.
        """
        if self._system != "Darwin":
            return None

        try:
            # First check if the keychain entry exists (without getting password)
            check_result = subprocess.run(
                [
                    "security",
                    "find-internet-password",
                    "-s",
                    "github.com",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if check_result.returncode != 0:
                return None

            # Entry exists, now try to get the password
            # This may prompt for Touch ID / password
            result = subprocess.run(
                [
                    "security",
                    "find-internet-password",
                    "-s",
                    "github.com",
                    "-g",  # Get password
                ],
                capture_output=True,
                text=True,
                timeout=30,  # Longer timeout for user authentication
            )

            if result.returncode != 0:
                return None

            # Parse the output
            # Password is in stderr, format: password: "xxx"
            stderr = result.stderr
            for line in stderr.split("\n"):
                if line.startswith("password:"):
                    # Extract password, handling quoted format
                    password = line.split("password:", 1)[1].strip()
                    if password.startswith('"') and password.endswith('"'):
                        password = password[1:-1]

                    if password and password.startswith("gho_"):
                        # Parse account from stdout
                        account = None
                        for out_line in result.stdout.split("\n"):
                            if '"acct"<blob>=' in out_line:
                                # Format: "acct"<blob>="username"
                                try:
                                    account = out_line.split("=", 1)[1].strip().strip('"')
                                except (IndexError, ValueError):
                                    pass

                        return DiscoveredToken(
                            token=password,
                            source="macOS Keychain (VS Code GitHub auth)",
                            account=account,
                        )

            return None

        except subprocess.TimeoutExpired:
            # User didn't authenticate in time, or keychain is locked
            return None
        except (FileNotFoundError, OSError):
            return None

        try:
            # Use security command to get the internet password
            result = subprocess.run(
                [
                    "security",
                    "find-internet-password",
                    "-s",
                    "github.com",
                    "-g",  # Get password
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode != 0:
                return None

            # Parse the output
            # Password is in stderr, format: password: "xxx"
            stderr = result.stderr
            for line in stderr.split("\n"):
                if line.startswith("password:"):
                    # Extract password, handling quoted format
                    password = line.split("password:", 1)[1].strip()
                    if password.startswith('"') and password.endswith('"'):
                        password = password[1:-1]

                    if password and password.startswith("gho_"):
                        # Parse account from stdout
                        account = None
                        for out_line in result.stdout.split("\n"):
                            if '"acct"<blob>=' in out_line:
                                # Format: "acct"<blob>="username"
                                try:
                                    account = out_line.split("=", 1)[1].strip().strip('"')
                                except (IndexError, ValueError):
                                    pass

                        return DiscoveredToken(
                            token=password,
                            source="macOS Keychain (VS Code GitHub auth)",
                            account=account,
                        )

            return None

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return None

    def _from_copilot_config(self) -> Optional[DiscoveredToken]:
        """
        Read token from GitHub Copilot config files.

        Checks:
        - ~/.config/github-copilot/hosts.json
        - ~/.config/github-copilot/apps.json
        """
        config_paths = self._get_copilot_config_paths()

        for config_path in config_paths:
            if not config_path.exists():
                continue

            try:
                with open(config_path, "r") as f:
                    data = json.load(f)

                # hosts.json format: {"github.com": {"oauth_token": "..."}}
                # apps.json format: {"github.com": {"oauth_token": "..."}}
                github_data = data.get("github.com", {})
                token = github_data.get("oauth_token")

                if token:
                    return DiscoveredToken(
                        token=token,
                        source=f"Copilot config: {config_path}",
                        account=github_data.get("user"),
                    )

            except (json.JSONDecodeError, IOError, KeyError):
                continue

        return None

    def _from_gh_cli(self) -> Optional[DiscoveredToken]:
        """
        Read token from gh CLI configuration.

        The gh CLI stores tokens in:
        - ~/.config/gh/hosts.yml (Linux/macOS)
        - %APPDATA%/gh/hosts.yml (Windows)
        """
        config_path = self._get_gh_config_path()

        if not config_path or not config_path.exists():
            return None

        try:
            # Try to read as YAML (simple parsing without PyYAML)
            with open(config_path, "r") as f:
                content = f.read()

            # Simple YAML parsing for gh hosts.yml
            # Format:
            # github.com:
            #     oauth_token: xxx
            #     user: xxx

            lines = content.split("\n")
            in_github = False
            token = None
            user = None

            for line in lines:
                stripped = line.strip()

                if stripped == "github.com:" or stripped.startswith("github.com:"):
                    in_github = True
                    continue

                if in_github:
                    if stripped.startswith("oauth_token:"):
                        token = stripped.split(":", 1)[1].strip()
                    elif stripped.startswith("user:"):
                        user = stripped.split(":", 1)[1].strip()
                    elif not line.startswith(" ") and not line.startswith("\t") and stripped:
                        # New top-level key, stop parsing
                        break

            if token:
                return DiscoveredToken(token=token, source="gh CLI config", account=user)

        except (IOError, OSError):
            pass

        return None

    def _get_copilot_config_paths(self) -> list[Path]:
        """Get potential paths for Copilot config files."""
        paths = []

        if self._system == "Windows":
            local_app_data = os.environ.get("LOCALAPPDATA", "")
            if local_app_data:
                base = Path(local_app_data) / "github-copilot"
                paths.extend([base / "hosts.json", base / "apps.json"])
        else:
            # Linux/macOS
            config_dir = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
            base = Path(config_dir) / "github-copilot"
            paths.extend([base / "hosts.json", base / "apps.json"])

        return paths

    def _get_gh_config_path(self) -> Optional[Path]:
        """Get path to gh CLI config."""
        if self._system == "Windows":
            app_data = os.environ.get("APPDATA", "")
            if app_data:
                return Path(app_data) / "gh" / "hosts.yml"
        else:
            config_dir = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
            return Path(config_dir) / "gh" / "hosts.yml"

        return None


# Convenience function
def discover_github_token() -> Optional[DiscoveredToken]:
    """
    Discover a GitHub token from system sources.

    This is the recommended way to get a token for Copilot access.

    Returns:
        DiscoveredToken if found, None otherwise
    """
    return SystemTokenDiscovery().discover()


async def verify_token_for_copilot(token: str) -> Tuple[bool, Optional[dict]]:
    """
    Verify that a GitHub token can be used for Copilot API access.

    Args:
        token: GitHub OAuth token to verify

    Returns:
        Tuple of (is_valid, copilot_response_data or None)
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://api.github.com/copilot_internal/v2/token",
                headers={
                    "Authorization": f"Token {token}",
                    "Accept": "application/json",
                    "User-Agent": "vecna/0.1.0",
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return True, data
                return False, None
    except Exception:
        return False, None
