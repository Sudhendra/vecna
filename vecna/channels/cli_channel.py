"""CLI channel adapter — wraps existing Rich CLI as a channel."""

import logging
from typing import AsyncIterator

from vecna.channels.base import (
    BaseChannel,
    ChannelCapability,
    InboundMessage,
    OutboundMessage,
)

logger = logging.getLogger("vecna.channels.cli")


class CLIChannel(BaseChannel):
    """The existing CLI/TUI as a channel adapter."""

    name = "cli"
    capabilities = [
        ChannelCapability.TEXT,
        ChannelCapability.STREAMING,
        ChannelCapability.RICH_TEXT,
    ]

    async def send(self, message: OutboundMessage) -> bool:
        """Print to console via Rich."""
        if not isinstance(message, OutboundMessage):
            raise TypeError("message must be an OutboundMessage")
        if not isinstance(message.content, str):
            raise TypeError("message.content must be a string")

        # TODO: Wire to existing Rich console in cli/main.py
        print(message.content)
        return True

    async def receive(self) -> AsyncIterator[InboundMessage]:
        """Read from stdin."""
        # Placeholder — actual implementation wraps existing Click REPL
        return
        yield  # type: ignore[misc]

    async def start(self) -> None:
        """Start CLI channel (no-op for CLI)."""
        logger.debug("CLI channel started")

    async def stop(self) -> None:
        """Stop CLI channel (no-op for CLI)."""
        logger.debug("CLI channel stopped")
