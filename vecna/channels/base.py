"""
Base channel adapter.

Every channel (CLI, iMessage, WhatsApp, Slack, etc.) implements this ABC.
Channels handle inbound/outbound message routing.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger("vecna.channels")


class ChannelCapability(Enum):
    """What a channel can do."""

    TEXT = "text"
    IMAGES = "images"
    FILES = "files"
    AUDIO = "audio"
    VIDEO = "video"
    REACTIONS = "reactions"
    THREADS = "threads"
    STREAMING = "streaming"
    RICH_TEXT = "rich_text"  # Markdown, HTML


@dataclass
class InboundMessage:
    """A message received from a channel."""

    channel: str
    sender: str
    content: str
    message_type: str = "text"
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    reply_to: Optional[str] = None  # For threaded channels


@dataclass
class OutboundMessage:
    """A message to send through a channel."""

    channel: str
    recipient: str
    content: str
    message_type: str = "text"
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None


class BaseChannel(ABC):
    """Abstract base class for all channel adapters."""

    name: str = "unnamed"
    capabilities: List[ChannelCapability] = []

    @abstractmethod
    async def send(self, message: OutboundMessage) -> bool:
        """Send a message through this channel."""
        ...

    @abstractmethod
    async def receive(self) -> AsyncIterator[InboundMessage]:
        """Stream inbound messages from this channel."""
        ...

    @abstractmethod
    async def start(self) -> None:
        """Start listening on this channel."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop listening."""
        ...
