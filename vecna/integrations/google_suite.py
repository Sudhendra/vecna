"""
Google Suite integration via gogcli CLI.

Wraps the gogcli command-line tool as a Vecna integration, providing:
- Calendar event awareness (read today's schedule)
- Email reading (unread count, important emails)
- Contact lookup
- Task management (Google Tasks)

All commands use --json output for structured parsing.
Credential storage is handled by gogcli's own secure keychain mechanism.
"""

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from vecna.core.types import SerializableMixin
from vecna.integrations.base import BaseIntegration, IntegrationStatus

logger = logging.getLogger("vecna.integrations.google_suite")


class GoogleSuiteCommand(Enum):
    """Available gogcli commands."""

    CALENDAR_LIST = "cal events list"
    GMAIL_LIST = "gmail messages list"
    CONTACTS_LIST = "contacts list"
    TASKS_LIST = "tasks list"

    def cli_args(self) -> List[str]:
        """Split command value into CLI argument list."""
        return self.value.split()


# Only safe read-only commands are allowed by default
COMMAND_ALLOWLIST: frozenset = frozenset(
    {
        GoogleSuiteCommand.CALENDAR_LIST,
        GoogleSuiteCommand.GMAIL_LIST,
        GoogleSuiteCommand.CONTACTS_LIST,
        GoogleSuiteCommand.TASKS_LIST,
    }
)


@dataclass
class GogcliResult(SerializableMixin):
    """Result of a gogcli command execution.

    Inherits to_dict() from SerializableMixin (Amendment 7).
    """

    success: bool = False
    command: str = ""
    data: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    raw_output: str = ""


class GoogleSuiteIntegration(BaseIntegration):
    """
    Google Suite integration using the gogcli CLI tool.

    gogcli handles its own OAuth2 authentication via the macOS keychain.
    This integration wraps it with subprocess execution, JSON parsing,
    and privacy-aware data handling.
    """

    name = "google_suite"
    description = "Google Suite integration (Calendar, Gmail, Contacts, Tasks) via gogcli"
    required_credentials: List[str] = []  # gogcli manages its own auth

    def __init__(self, binary_path: Optional[str] = None) -> None:
        self.binary_path = binary_path or "gogcli"
        self.enabled = False
        self._running = False

    def _check_binary(self) -> bool:
        """Check if gogcli binary is available on PATH."""
        return shutil.which(self.binary_path) is not None

    async def check_health(self) -> IntegrationStatus:
        """Check if gogcli is installed and accessible."""
        if self._check_binary():
            return IntegrationStatus(
                healthy=True,
                name=self.name,
                message="gogcli binary found and accessible",
            )
        return IntegrationStatus(
            healthy=False,
            name=self.name,
            message="gogcli binary not found or not installed",
        )

    async def start(self) -> None:
        """Start the Google Suite integration."""
        self._running = True
        logger.info("Google Suite integration started")

    async def stop(self) -> None:
        """Stop the Google Suite integration."""
        self._running = False
        logger.info("Google Suite integration stopped")

    def is_command_allowed(self, command_str: str) -> bool:
        """Check if a command string matches the allowlist."""
        for allowed in COMMAND_ALLOWLIST:
            if command_str.strip() == allowed.value:
                return True
        return False

    async def _exec_gogcli(self, args: List[str], timeout: float = 30.0) -> Tuple[int, str, str]:
        """Execute a gogcli subprocess and return (returncode, stdout, stderr)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.binary_path,
                *args,
                "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            logger.error("gogcli command timed out after %ss: %s", timeout, args)
            return (1, "", f"Command timed out after {timeout}s")
        except FileNotFoundError:
            logger.error("gogcli binary not found")
            return (1, "", "gogcli binary not found")
        except OSError as e:
            logger.error("gogcli execution error: %s", e)
            return (1, "", str(e))

    async def run_command(
        self,
        command: GoogleSuiteCommand,
        extra_args: Optional[List[str]] = None,
    ) -> GogcliResult:
        """Run a gogcli command and parse the JSON output."""
        args = command.cli_args()
        if extra_args:
            args.extend(extra_args)

        returncode, stdout, stderr = await self._exec_gogcli(args)

        if returncode != 0:
            return GogcliResult(
                success=False,
                command=command.value,
                error=stderr or f"gogcli exited with code {returncode}",
                raw_output=stdout,
            )

        # Parse JSON output
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, list):
                data = parsed
            elif isinstance(parsed, dict):
                data = [parsed]
            else:
                data = [{"value": parsed}]

            return GogcliResult(
                success=True,
                command=command.value,
                data=data,
                raw_output=stdout,
            )
        except json.JSONDecodeError as e:
            return GogcliResult(
                success=False,
                command=command.value,
                error=f"Failed to parse JSON output: {e}",
                raw_output=stdout,
            )

    # -- Convenience methods --

    async def get_calendar_events(self, max_results: int = 10) -> GogcliResult:
        """Get upcoming calendar events."""
        return await self.run_command(
            GoogleSuiteCommand.CALENDAR_LIST,
            extra_args=[f"--max={max_results}"],
        )

    async def get_emails(self, max_results: int = 5) -> GogcliResult:
        """Get recent emails."""
        return await self.run_command(
            GoogleSuiteCommand.GMAIL_LIST,
            extra_args=[f"--max={max_results}"],
        )

    async def get_contacts(self) -> GogcliResult:
        """Get contact list."""
        return await self.run_command(GoogleSuiteCommand.CONTACTS_LIST)

    async def get_tasks(self) -> GogcliResult:
        """Get Google Tasks."""
        return await self.run_command(GoogleSuiteCommand.TASKS_LIST)
