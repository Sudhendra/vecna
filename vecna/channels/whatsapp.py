"""
WhatsApp channel adapter via the wacli CLI.

Provides bidirectional WhatsApp communication:
- Inbound: ``wacli watch --json`` streams incoming messages
- Outbound: ``wacli send <number> <message>`` sends messages
- Search: ``wacli search <query> --json`` searches message history

wacli uses QR code authentication and stores message history
in a local SQLite database with FTS5 for full-text search.

All WhatsApp content is LOCAL_ONLY — never sent to cloud models.
"""

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from vecna.channels.base import (
    BaseChannel,
    ChannelCapability,
    InboundMessage,
    OutboundMessage,
)
from vecna.core.types import SerializableMixin

logger = logging.getLogger("vecna.channels.whatsapp")


class WacliParseError(Exception):
    """Raised when wacli JSON output cannot be parsed."""

    pass


@dataclass
class WacliConfig:
    """Configuration for the WhatsApp channel."""

    binary_path: str = "wacli"
    privacy_tier: str = "local_only"
    max_message_length: int = 65536
    search_limit: int = 50


@dataclass
class WacliResult(SerializableMixin):
    """Result of a wacli command execution.

    Inherits to_dict() from SerializableMixin (Amendment 7).
    """

    success: bool = False
    command: str = ""
    data: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    raw_output: str = ""


class WhatsAppChannel(BaseChannel):
    """
    WhatsApp channel adapter using the wacli CLI.

    Uses ``wacli watch --json`` for streaming inbound messages,
    ``wacli send <recipient> <message>`` for outbound delivery,
    and ``wacli search <query> --json`` for message history search.

    Authentication is handled by wacli via QR code scanning.
    Message history is stored locally in SQLite with FTS5.
    """

    name = "whatsapp"
    capabilities: List[ChannelCapability] = [
        ChannelCapability.TEXT,
        ChannelCapability.IMAGES,
        ChannelCapability.FILES,
    ]

    def __init__(self, config: Optional[WacliConfig] = None) -> None:
        self.config = config or WacliConfig()
        self.is_running: bool = False
        self._watch_process: Optional[asyncio.subprocess.Process] = None

    def _check_binary(self) -> bool:
        """Check if wacli binary is available on PATH."""
        return shutil.which(self.config.binary_path) is not None

    def parse_inbound(self, raw_json: str) -> Optional[InboundMessage]:
        """Parse a raw JSON line from ``wacli watch --json`` into an InboundMessage.

        Returns None for messages sent by the user themselves (is_from_me=True).

        Raises:
            WacliParseError: If the raw_json string is not valid JSON.
        """
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise WacliParseError(f"Invalid JSON from wacli: {e}") from e

        # Skip our own outgoing messages
        if data.get("is_from_me", False):
            return None

        sender = data.get("sender", "unknown")
        text = data.get("text", "")

        # WhatsApp uses "media" instead of "attachments"
        attachments: List[Dict[str, object]] = []
        for item in data.get("media", []):
            if isinstance(item, dict):
                attachments.append(item)

        metadata = {
            "chat_id": data.get("chat_id", ""),
            "sender_name": data.get("sender_name", ""),
            "privacy_tier": self.config.privacy_tier,
        }

        return InboundMessage(
            channel="whatsapp",
            sender=sender,
            content=text,
            message_type="text",
            attachments=attachments,
            metadata=metadata,
        )

    async def _exec_wacli(self, *args: str, timeout: float = 30.0) -> Tuple[int, str, str]:
        """Execute a wacli subprocess and return (returncode, stdout, stderr)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.config.binary_path,
                *args,
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
            return (1, "", f"wacli command timed out after {timeout}s")
        except FileNotFoundError:
            return (1, "", "wacli binary not found")
        except OSError as e:
            return (1, "", str(e))

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via WhatsApp.

        Truncates content to ``max_message_length`` if it exceeds the limit.
        Returns True on success, False on failure.
        """
        recipient = message.recipient
        content = message.content

        # Truncate if needed
        if len(content) > self.config.max_message_length:
            content = content[: self.config.max_message_length]

        returncode, _stdout, stderr = await self._exec_wacli("send", recipient, content)

        if returncode != 0:
            logger.error("Failed to send WhatsApp message to %s: %s", recipient, stderr)
            return False

        logger.info("Sent WhatsApp message to %s (%d chars)", recipient, len(content))
        return True

    async def search(self, query: str, limit: Optional[int] = None) -> WacliResult:
        """Search WhatsApp message history.

        Uses ``wacli search <query> --json --limit=N`` to query
        the local SQLite FTS5 index.
        """
        search_limit = limit or self.config.search_limit
        returncode, stdout, stderr = await self._exec_wacli(
            "search", query, "--json", f"--limit={search_limit}"
        )

        if returncode != 0:
            return WacliResult(
                success=False,
                command="search",
                error=stderr or f"wacli search exited with code {returncode}",
                raw_output=stdout,
            )

        try:
            parsed = json.loads(stdout)
            data = parsed if isinstance(parsed, list) else [parsed]
            return WacliResult(
                success=True,
                command="search",
                data=data,
                raw_output=stdout,
            )
        except json.JSONDecodeError as e:
            return WacliResult(
                success=False,
                command="search",
                error=f"Failed to parse JSON output: {e}",
                raw_output=stdout,
            )

    async def _start_watch_process(self) -> None:
        """Start the ``wacli watch --json`` subprocess."""
        self._watch_process = await asyncio.create_subprocess_exec(
            self.config.binary_path,
            "watch",
            "--json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("Started wacli watch process")

    async def receive(self) -> AsyncIterator[InboundMessage]:
        """Stream inbound messages from the wacli watch process."""
        if not self._watch_process or not self._watch_process.stdout:
            return

        async for line in self._watch_process.stdout:
            raw = line.decode("utf-8", errors="replace").strip()
            if not raw:
                continue

            try:
                msg = self.parse_inbound(raw)
                if msg is not None:
                    yield msg
            except WacliParseError as e:
                logger.warning("Failed to parse wacli output: %s", e)
                continue

    async def start(self) -> None:
        """Start the WhatsApp channel (begins watching for messages).

        Raises:
            RuntimeError: If the wacli binary is not found.
        """
        if not self._check_binary():
            raise RuntimeError(
                f"wacli binary not found at '{self.config.binary_path}'. "
                f"Install with: brew install wacli"
            )

        await self._start_watch_process()
        self.is_running = True
        logger.info("WhatsApp channel started")

    async def stop(self) -> None:
        """Stop the WhatsApp channel."""
        if self._watch_process:
            try:
                self._watch_process.terminate()
                await self._watch_process.wait()
            except OSError as e:
                logger.error("Error stopping wacli watch: %s", e)
            self._watch_process = None

        self.is_running = False
        logger.info("WhatsApp channel stopped")
