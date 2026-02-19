"""
iMessage channel adapter via the imsg CLI.

Provides bidirectional iMessage communication:
- Inbound: ``imsg watch --json`` streams incoming messages
- Outbound: ``imsg send <number> <message>`` sends messages

macOS only. Requires Full Disk Access for iMessage database reading.
All iMessage content is LOCAL_ONLY — never sent to cloud models.
"""

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from typing import AsyncIterator, Dict, List, Optional, Tuple

from vecna.channels.base import (
    BaseChannel,
    ChannelCapability,
    InboundMessage,
    OutboundMessage,
)

logger = logging.getLogger("vecna.channels.imessage")


class ImsgParseError(Exception):
    """Raised when an imsg JSON message cannot be parsed."""

    pass


@dataclass
class ImsgConfig:
    """Configuration for the iMessage channel."""

    binary_path: str = "imsg"
    watch_timeout: int = 0  # 0 = indefinite
    privacy_tier: str = "local_only"
    max_message_length: int = 10000


class iMessageChannel(BaseChannel):
    """
    iMessage channel adapter using the imsg CLI.

    Uses ``imsg watch --json`` for streaming inbound messages and
    ``imsg send <recipient> <message>`` for outbound delivery.
    """

    name = "imessage"
    capabilities: List[ChannelCapability] = [
        ChannelCapability.TEXT,
        ChannelCapability.IMAGES,
    ]

    def __init__(self, config: Optional[ImsgConfig] = None) -> None:
        self.config = config or ImsgConfig()
        self.is_running: bool = False
        self._watch_process: Optional[asyncio.subprocess.Process] = None

    def _check_binary(self) -> bool:
        """Check if imsg binary is available on PATH."""
        return shutil.which(self.config.binary_path) is not None

    def parse_inbound(self, raw_json: str) -> Optional[InboundMessage]:
        """Parse a raw JSON line from ``imsg watch --json`` into an InboundMessage.

        Returns None for messages sent by the user themselves (is_from_me=True).

        Raises:
            ImsgParseError: If the raw_json string is not valid JSON.
        """
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError as e:
            raise ImsgParseError(f"Invalid JSON from imsg: {e}") from e

        # Skip our own outgoing messages
        if data.get("is_from_me", False):
            return None

        sender = data.get("sender", "unknown")
        text = data.get("text", "")

        attachments: List[Dict[str, object]] = []
        for att in data.get("attachments", []):
            if isinstance(att, dict):
                attachments.append(att)

        metadata = {
            "chat_id": data.get("chat_id", ""),
            "privacy_tier": self.config.privacy_tier,
        }

        return InboundMessage(
            channel="imessage",
            sender=sender,
            content=text,
            message_type="text",
            attachments=attachments,
            metadata=metadata,
        )

    async def _exec_imsg_send(self, recipient: str, text: str) -> Tuple[int, str, str]:
        """Execute ``imsg send <recipient> <text>`` and return (code, stdout, stderr)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.config.binary_path,
                "send",
                recipient,
                text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)
            return (
                proc.returncode or 0,
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
            )
        except asyncio.TimeoutError:
            return (1, "", "imsg send timed out")
        except FileNotFoundError:
            return (1, "", "imsg binary not found")
        except OSError as e:
            return (1, "", str(e))

    async def send(self, message: OutboundMessage) -> bool:
        """Send a message via iMessage.

        Truncates content to ``max_message_length`` if it exceeds the limit.
        Returns True on success, False on failure.
        """
        recipient = message.recipient
        content = message.content

        # Truncate if needed
        if len(content) > self.config.max_message_length:
            content = content[: self.config.max_message_length]

        returncode, _stdout, stderr = await self._exec_imsg_send(recipient, content)

        if returncode != 0:
            logger.error("Failed to send iMessage to %s: %s", recipient, stderr)
            return False

        logger.info("Sent iMessage to %s (%d chars)", recipient, len(content))
        return True

    async def _start_watch_process(self) -> None:
        """Start the ``imsg watch --json`` subprocess."""
        args = [self.config.binary_path, "watch", "--json"]
        self._watch_process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        logger.info("Started imsg watch process")

    async def receive(self) -> AsyncIterator[InboundMessage]:
        """Stream inbound messages from the imsg watch process."""
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
            except ImsgParseError as e:
                logger.warning("Failed to parse imsg output: %s", e)
                continue

    async def start(self) -> None:
        """Start the iMessage channel (begins watching for messages).

        Raises:
            RuntimeError: If the imsg binary is not found.
        """
        if not self._check_binary():
            raise RuntimeError(
                f"imsg binary not found at '{self.config.binary_path}'. "
                f"Install with: brew install imsg"
            )

        await self._start_watch_process()
        self.is_running = True
        logger.info("iMessage channel started")

    async def stop(self) -> None:
        """Stop the iMessage channel."""
        if self._watch_process:
            try:
                self._watch_process.terminate()
                await self._watch_process.wait()
            except OSError as e:
                logger.error("Error stopping imsg watch: %s", e)
            self._watch_process = None

        self.is_running = False
        logger.info("iMessage channel stopped")
