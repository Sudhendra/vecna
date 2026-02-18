"""Unified Message Router for cross-channel dispatch.

Routes inbound messages from any channel through HiveLoop and
dispatches responses back through the originating channel.
Maintains per-session conversation context across channels.

Amendment 3: MessageRouter is the single entry point for ALL inbound messages.
HTTP server routes (/api/chat, /ws/stream) MUST delegate to
MessageRouter.route_inbound(), NOT call HiveLoop.think() directly.
"""

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from vecna.core.types import SerializableMixin

logger = logging.getLogger("vecna.channels.router")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class UnknownChannelError(Exception):
    """Raised when routing to an unregistered channel."""


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""


class RoutingError(Exception):
    """Raised when message routing fails (e.g., HiveLoop error)."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SessionContext(SerializableMixin):
    """Conversation session state.

    Tracks which channel a session originated from and
    maintains conversation history for context continuity.

    Attributes:
        session_id: Unique session identifier.
        channel_name: Channel this session originated from.
        history: List of message dicts with "role" and "content".
        created_at: When the session was created.
    """

    session_id: str = ""
    channel_name: str = ""
    history: List[Dict[str, str]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class InboundMessage(SerializableMixin):
    """An inbound message from a channel.

    Attributes:
        content: The message text.
        channel_name: Which channel sent the message.
        session_id: Session identifier for context tracking.
        metadata: Optional extra context from the channel.
    """

    content: str = ""
    channel_name: str = ""
    session_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage(SerializableMixin):
    """An outbound response to a channel.

    Attributes:
        content: The formatted response text.
        channel_name: Target channel.
        session_id: Session this response belongs to.
        format_type: Output format (plain, markdown, rich).
    """

    content: str = ""
    channel_name: str = ""
    session_id: str = ""
    format_type: str = "plain"


# ---------------------------------------------------------------------------
# MessageRouter
# ---------------------------------------------------------------------------


class MessageRouter:
    """Routes messages between channels and HiveLoop.

    Maintains a channel registry and session map. Inbound messages are
    dispatched to HiveLoop.think(), and responses are formatted for the
    originating channel before return.

    Amendment 3: This is the single entry point for ALL inbound messages.
    Amendment 11: All state is accessible via public methods.

    Args:
        hive_loop: Optional HiveLoop instance for processing messages.
        rate_limit_rpm: Maximum requests per rate-limit window.
        rate_limit_window_seconds: Duration of rate-limit window in seconds.
    """

    def __init__(
        self,
        hive_loop: Any = None,
        rate_limit_rpm: int = 60,
        rate_limit_window_seconds: float = 60.0,
    ) -> None:
        self._channels: Dict[str, Any] = {}
        self._sessions: Dict[str, SessionContext] = {}
        self._hive_loop: Any = hive_loop
        self._rate_limit_rpm: int = rate_limit_rpm
        self._rate_limit_window: float = rate_limit_window_seconds
        self._request_timestamps: List[float] = []
        self._lock: asyncio.Lock = asyncio.Lock()
        self._format_map: Dict[str, str] = {
            "cli": "rich",
            "sms": "plain",
            "slack": "markdown",
            "discord": "markdown",
        }

    # -------------------------------------------------------------------
    # Channel registry (public interface)
    # -------------------------------------------------------------------

    def register_channel(self, name: str, channel: Any) -> None:
        """Register a channel for message routing.

        Args:
            name: Channel identifier.
            channel: Channel object with a send() method.
        """
        self._channels[name] = channel
        logger.info("Channel registered: %s", name)

    def unregister_channel(self, name: str) -> None:
        """Remove a channel from the registry.

        Args:
            name: Channel identifier to remove.
        """
        self._channels.pop(name, None)
        logger.info("Channel unregistered: %s", name)

    def list_channels(self) -> List[str]:
        """List registered channel names.

        Returns:
            List of channel name strings.
        """
        return list(self._channels.keys())

    # -------------------------------------------------------------------
    # Message routing (core)
    # -------------------------------------------------------------------

    async def route_inbound(self, message: InboundMessage) -> OutboundMessage:
        """Route an inbound message through HiveLoop.

        Creates or retrieves the session, validates the message,
        checks rate limits, passes the message content to
        HiveLoop.think(), records history, and returns a formatted
        OutboundMessage.

        Args:
            message: The inbound message to route.

        Returns:
            Formatted OutboundMessage with the response.

        Raises:
            ValueError: If message content or session_id is empty.
            UnknownChannelError: If channel is not registered.
            RateLimitError: If rate limit is exceeded.
            RoutingError: If HiveLoop is not connected or fails.
        """
        # Validate input
        if not message.session_id or not message.session_id.strip():
            raise ValueError("session_id must not be empty")

        if not message.content or not message.content.strip():
            raise ValueError("Message content must not be empty")

        if message.channel_name not in self._channels:
            raise UnknownChannelError(f"Channel not registered: {message.channel_name}")

        # Check rate limit
        self._check_rate_limit()

        # Ensure HiveLoop is connected
        if self._hive_loop is None:
            raise RoutingError("HiveLoop not connected to router")

        # Get or create session (thread-safe)
        async with self._lock:
            session = self._get_or_create_session(
                message.session_id,
                message.channel_name,
            )
            session.history.append(
                {
                    "role": "user",
                    "content": message.content,
                }
            )

        # Call HiveLoop outside the lock to avoid blocking
        try:
            response_text = await self._hive_loop.think(message.content)
        except RuntimeError as exc:
            raise RoutingError(str(exc)) from exc

        # Record assistant response in session
        async with self._lock:
            session.history.append(
                {
                    "role": "assistant",
                    "content": response_text,
                }
            )

        # Format for channel
        formatted = self.format_for_channel(response_text, message.channel_name)
        format_type = self._format_map.get(message.channel_name, "plain")

        return OutboundMessage(
            content=formatted,
            channel_name=message.channel_name,
            session_id=message.session_id,
            format_type=format_type,
        )

    # -------------------------------------------------------------------
    # Format adaptation (public, Amendment 11)
    # -------------------------------------------------------------------

    def format_for_channel(self, text: str, channel_name: str) -> str:
        """Format response text for a specific channel.

        - cli: preserve rich markup
        - sms: strip all markdown to plain text
        - slack/discord: preserve markdown
        - unknown: return as-is

        Args:
            text: Raw response text.
            channel_name: Target channel name.

        Returns:
            Formatted text string.
        """
        if channel_name == "sms":
            stripped = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
            stripped = re.sub(r"\*(.+?)\*", r"\1", stripped)
            stripped = re.sub(r"_(.+?)_", r"\1", stripped)
            stripped = re.sub(r"`(.+?)`", r"\1", stripped)
            return stripped
        return text

    # -------------------------------------------------------------------
    # Session management (public, Amendment 11)
    # -------------------------------------------------------------------

    def get_session(self, session_id: str) -> Optional[SessionContext]:
        """Get a session by ID.

        Args:
            session_id: The session to look up.

        Returns:
            SessionContext or None if not found.
        """
        return self._sessions.get(session_id)

    def get_session_count(self) -> int:
        """Get the number of active sessions.

        Returns:
            Count of active sessions.
        """
        return len(self._sessions)

    def get_active_sessions(self) -> List[SessionContext]:
        """Get all active sessions.

        Returns:
            List of active SessionContext objects.
        """
        return list(self._sessions.values())

    def close_session(self, session_id: str) -> None:
        """Close and remove a session.

        Args:
            session_id: The session to close.
        """
        self._sessions.pop(session_id, None)
        logger.debug("Session closed: %s", session_id)

    # -------------------------------------------------------------------
    # Serialization
    # -------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serialize router state.

        Returns:
            Dict with channels, sessions, and rate limit info.
        """
        return {
            "channels": list(self._channels.keys()),
            "sessions": {sid: s.to_dict() for sid, s in self._sessions.items()},
            "rate_limit_rpm": self._rate_limit_rpm,
        }

    # -------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------

    def _get_or_create_session(
        self,
        session_id: str,
        channel_name: str,
    ) -> SessionContext:
        """Get existing session or create a new one.

        Must be called under self._lock for thread safety.

        Args:
            session_id: Session identifier.
            channel_name: Channel the session belongs to.

        Returns:
            The SessionContext for this session.
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionContext(
                session_id=session_id,
                channel_name=channel_name,
            )
            logger.debug(
                "Created session %s on channel %s",
                session_id,
                channel_name,
            )
        return self._sessions[session_id]

    def _check_rate_limit(self) -> None:
        """Check and enforce rate limiting.

        Raises:
            RateLimitError: If rate limit is exceeded.
        """
        now = time.monotonic()
        cutoff = now - self._rate_limit_window

        # Prune old timestamps
        self._request_timestamps = [ts for ts in self._request_timestamps if ts > cutoff]

        if len(self._request_timestamps) >= self._rate_limit_rpm:
            raise RateLimitError(
                f"Rate limit exceeded: {self._rate_limit_rpm} requests "
                f"per {self._rate_limit_window}s window"
            )

        self._request_timestamps.append(now)
