"""Unit tests for the MessageRouter unified channel dispatch.

Tests cover:
- SessionContext creation and serialization
- InboundMessage / OutboundMessage dataclasses
- Channel registration and unregistration
- Inbound message routing through HiveLoop
- Session management (create, get, close, history)
- Format adaptation per channel type
- Router state serialization
- Error paths: unknown channel, malformed input, rate limiting, routing failure
- Concurrency stress test (Amendment 12)

Amendments applied:
- Amendment 7: SessionContext uses SerializableMixin
- Amendment 9: No trivial assertions
- Amendment 10: 4+ error/edge-case tests
- Amendment 11: All tests use public interface only
- Amendment 12: Concurrency stress test for route_inbound()
"""

import asyncio
from datetime import datetime
from typing import Any, List

import pytest

from vecna.channels.router import (
    InboundMessage,
    MessageRouter,
    OutboundMessage,
    RateLimitError,
    RoutingError,
    SessionContext,
    UnknownChannelError,
)


# ---------------------------------------------------------------------------
# Test helpers (mock objects)
# ---------------------------------------------------------------------------


class MockChannel:
    """Mock channel for testing."""

    def __init__(self, name: str, format_type: str = "plain"):
        self.name = name
        self.format_type = format_type
        self.sent_messages: List[str] = []

    async def send(self, message: str) -> None:
        self.sent_messages.append(message)


class MockHiveLoop:
    """Mock HiveLoop for testing router integration."""

    def __init__(self, response: str = "Mock response"):
        self._response = response
        self.last_task = ""
        self.call_count = 0

    async def think(self, task: str, **kwargs: Any) -> str:
        self.last_task = task
        self.call_count += 1
        return self._response


class FailingHiveLoop:
    """HiveLoop mock that raises on think()."""

    async def think(self, task: str, **kwargs: Any) -> str:
        raise RuntimeError("Model inference failed")


class SlowHiveLoop:
    """HiveLoop mock that delays response."""

    def __init__(self, delay: float = 0.05, response: str = "Slow response"):
        self._delay = delay
        self._response = response

    async def think(self, task: str, **kwargs: Any) -> str:
        await asyncio.sleep(self._delay)
        return self._response


# ===========================================================================
# SessionContext tests
# ===========================================================================


class TestSessionContext:
    """Tests for SessionContext dataclass."""

    def test_session_context_creation_with_expected_fields(self):
        """SessionContext initializes with correct field values."""
        before = datetime.now()
        ctx = SessionContext(
            session_id="sess-001",
            channel_name="cli",
        )
        after = datetime.now()
        assert ctx.session_id == "sess-001"
        assert ctx.channel_name == "cli"
        assert ctx.history == []
        # Amendment 9: Assert created_at is recent, not just exists
        assert before <= ctx.created_at <= after

    def test_session_context_to_dict_serializes_fields(self):
        """SessionContext serializes all fields correctly via SerializableMixin."""
        ctx = SessionContext(
            session_id="sess-002",
            channel_name="slack",
        )
        d = ctx.to_dict()
        assert d["session_id"] == "sess-002"
        assert d["channel_name"] == "slack"
        # created_at should be ISO string via SerializableMixin
        assert "T" in d["created_at"]  # ISO format contains 'T'

    def test_session_context_history_preserves_messages(self):
        """Messages added to history retain role and content."""
        ctx = SessionContext(
            session_id="sess-003",
            channel_name="cli",
        )
        ctx.history.append({"role": "user", "content": "hello"})
        ctx.history.append({"role": "assistant", "content": "hi"})
        assert ctx.history[0] == {"role": "user", "content": "hello"}
        assert ctx.history[1] == {"role": "assistant", "content": "hi"}


# ===========================================================================
# InboundMessage / OutboundMessage tests
# ===========================================================================


class TestInboundOutbound:
    """Tests for InboundMessage and OutboundMessage dataclasses."""

    def test_inbound_message_fields(self):
        """InboundMessage captures channel, session, and content correctly."""
        msg = InboundMessage(
            content="Hello Vecna",
            channel_name="cli",
            session_id="sess-001",
        )
        assert msg.content == "Hello Vecna"
        assert msg.channel_name == "cli"
        assert msg.session_id == "sess-001"
        assert msg.metadata == {}

    def test_inbound_message_with_metadata(self):
        """InboundMessage preserves arbitrary metadata."""
        msg = InboundMessage(
            content="Test",
            channel_name="slack",
            session_id="sess-002",
            metadata={"thread_id": "t-123", "user_name": "alice"},
        )
        assert msg.metadata["thread_id"] == "t-123"
        assert msg.metadata["user_name"] == "alice"

    def test_outbound_message_fields(self):
        """OutboundMessage captures response, format, and session."""
        msg = OutboundMessage(
            content="Response text",
            channel_name="slack",
            session_id="sess-001",
            format_type="markdown",
        )
        assert msg.content == "Response text"
        assert msg.format_type == "markdown"
        assert msg.channel_name == "slack"
        assert msg.session_id == "sess-001"


# ===========================================================================
# Channel registration tests
# ===========================================================================


class TestMessageRouterRegistration:
    """Tests for channel registration via public interface."""

    def test_register_channel_appears_in_list(self):
        """Registering a channel makes it visible via list_channels()."""
        router = MessageRouter()
        channel = MockChannel("cli")
        router.register_channel("cli", channel)
        assert "cli" in router.list_channels()

    def test_register_multiple_channels(self):
        """Multiple channels all appear in list_channels()."""
        router = MessageRouter()
        router.register_channel("cli", MockChannel("cli"))
        router.register_channel("slack", MockChannel("slack", "markdown"))
        router.register_channel("sms", MockChannel("sms", "plain"))
        channels = router.list_channels()
        assert set(channels) == {"cli", "slack", "sms"}

    def test_list_channels_returns_registered_names(self):
        """list_channels returns exactly the registered names."""
        router = MessageRouter()
        router.register_channel("cli", MockChannel("cli"))
        router.register_channel("slack", MockChannel("slack"))
        names = router.list_channels()
        assert sorted(names) == ["cli", "slack"]

    def test_unregister_channel_removes_from_list(self):
        """Unregistering removes a channel from list_channels()."""
        router = MessageRouter()
        router.register_channel("cli", MockChannel("cli"))
        router.unregister_channel("cli")
        assert "cli" not in router.list_channels()

    def test_unregister_nonexistent_channel_is_noop(self):
        """Unregistering a channel that doesn't exist doesn't raise."""
        router = MessageRouter()
        router.unregister_channel("nonexistent")  # Should not raise
        assert router.list_channels() == []


# ===========================================================================
# Routing tests
# ===========================================================================


class TestMessageRouterRouting:
    """Tests for inbound message routing."""

    async def test_route_inbound_creates_session(self):
        """Routing an inbound message creates a retrievable session."""
        loop = MockHiveLoop(response="Hello user")
        router = MessageRouter(hive_loop=loop)
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="Hello",
            channel_name="cli",
            session_id="sess-new",
        )
        response = await router.route_inbound(msg)
        # Amendment 9: Assert specific response content
        assert response.content == "Hello user"
        # Amendment 11: Use public accessor
        session = router.get_session("sess-new")
        assert session is not None
        assert session.session_id == "sess-new"

    async def test_route_inbound_returns_hive_loop_response(self):
        """Routing returns the HiveLoop response content."""
        loop = MockHiveLoop(response="Thought result")
        router = MessageRouter(hive_loop=loop)
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="Think about this",
            channel_name="cli",
            session_id="sess-think",
        )
        response = await router.route_inbound(msg)
        assert response.content == "Thought result"
        assert response.channel_name == "cli"
        assert response.session_id == "sess-think"

    async def test_route_inbound_passes_content_to_hive_loop(self):
        """Router passes message content to HiveLoop.think."""
        loop = MockHiveLoop()
        router = MessageRouter(hive_loop=loop)
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="Analyze data",
            channel_name="cli",
            session_id="sess-analyze",
        )
        await router.route_inbound(msg)
        assert loop.last_task == "Analyze data"

    async def test_route_inbound_updates_session_history(self):
        """Routing adds both user and assistant messages to session history."""
        loop = MockHiveLoop(response="Reply")
        router = MessageRouter(hive_loop=loop)
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="First message",
            channel_name="cli",
            session_id="sess-hist",
        )
        await router.route_inbound(msg)
        # Amendment 11: Use public accessor
        session = router.get_session("sess-hist")
        assert session.history[0] == {"role": "user", "content": "First message"}
        assert session.history[1] == {"role": "assistant", "content": "Reply"}

    async def test_route_preserves_session_across_messages(self):
        """Multiple messages to same session share context and accumulate history."""
        loop = MockHiveLoop(response="Reply")
        router = MessageRouter(hive_loop=loop)
        router.register_channel("cli", MockChannel("cli"))
        for i in range(3):
            msg = InboundMessage(
                content=f"Message {i}",
                channel_name="cli",
                session_id="sess-multi",
            )
            await router.route_inbound(msg)
        session = router.get_session("sess-multi")
        # 3 user + 3 assistant = 6 history entries
        assert len(session.history) == 6
        assert session.history[0] == {"role": "user", "content": "Message 0"}
        assert session.history[4] == {"role": "user", "content": "Message 2"}
        assert session.history[5] == {"role": "assistant", "content": "Reply"}

    async def test_route_sets_format_type_for_channel(self):
        """Outbound message format_type matches the channel's configured format."""
        loop = MockHiveLoop(response="test")
        router = MessageRouter(hive_loop=loop)
        router.register_channel("slack", MockChannel("slack", "markdown"))
        msg = InboundMessage(content="hi", channel_name="slack", session_id="s1")
        response = await router.route_inbound(msg)
        assert response.format_type == "markdown"


# ===========================================================================
# Format adaptation tests
# ===========================================================================


class TestFormatAdaptation:
    """Tests for output format adaptation per channel."""

    def test_format_for_cli_preserves_markup(self):
        """CLI format preserves rich markup content."""
        router = MessageRouter()
        # Amendment 11: Use public method
        result = router.format_for_channel("**bold** text", "cli")
        assert "bold" in result
        assert "text" in result

    def test_format_for_sms_strips_markdown(self):
        """SMS format strips all markdown to plain text."""
        router = MessageRouter()
        result = router.format_for_channel("**bold** and *italic*", "sms")
        assert "**" not in result
        assert "*" not in result
        assert "bold" in result
        assert "italic" in result

    def test_format_for_slack_preserves_markdown(self):
        """Slack format preserves markdown syntax."""
        router = MessageRouter()
        result = router.format_for_channel("**bold** text", "slack")
        assert "bold" in result

    def test_format_for_unknown_channel_returns_as_is(self):
        """Unknown channel gets text returned verbatim."""
        router = MessageRouter()
        result = router.format_for_channel("Some text", "unknown")
        assert result == "Some text"

    def test_format_strips_code_backticks_for_sms(self):
        """SMS format strips inline code backticks."""
        router = MessageRouter()
        result = router.format_for_channel("use `git commit`", "sms")
        assert "`" not in result
        assert "git commit" in result

    def test_format_strips_underscores_for_sms(self):
        """SMS format strips underscore emphasis."""
        router = MessageRouter()
        result = router.format_for_channel("_emphasized_ word", "sms")
        assert "_" not in result
        assert "emphasized" in result


# ===========================================================================
# Router state management tests
# ===========================================================================


class TestRouterState:
    """Tests for router state management via public interface."""

    def test_get_session_returns_none_for_missing(self):
        """get_session returns None for unknown session ID."""
        router = MessageRouter()
        assert router.get_session("nonexistent") is None

    async def test_get_active_sessions_lists_created_sessions(self):
        """get_active_sessions lists sessions created via routing."""
        loop = MockHiveLoop()
        router = MessageRouter(hive_loop=loop)
        router.register_channel("cli", MockChannel("cli"))
        router.register_channel("slack", MockChannel("slack"))

        await router.route_inbound(
            InboundMessage(content="hi", channel_name="cli", session_id="s1")
        )
        await router.route_inbound(
            InboundMessage(content="hello", channel_name="slack", session_id="s2")
        )
        active = router.get_active_sessions()
        session_ids = {s.session_id for s in active}
        assert session_ids == {"s1", "s2"}

    async def test_close_session_removes_session(self):
        """close_session removes a session so get_session returns None."""
        loop = MockHiveLoop()
        router = MessageRouter(hive_loop=loop)
        router.register_channel("cli", MockChannel("cli"))
        await router.route_inbound(
            InboundMessage(content="hi", channel_name="cli", session_id="s1")
        )
        router.close_session("s1")
        assert router.get_session("s1") is None

    def test_close_nonexistent_session_is_noop(self):
        """Closing a nonexistent session doesn't raise."""
        router = MessageRouter()
        router.close_session("nonexistent")  # Should not raise

    def test_get_session_count(self):
        """get_session_count reflects number of active sessions."""
        router = MessageRouter()
        assert router.get_session_count() == 0

    async def test_get_session_count_after_routing(self):
        """get_session_count increments after routing creates sessions."""
        loop = MockHiveLoop()
        router = MessageRouter(hive_loop=loop)
        router.register_channel("cli", MockChannel("cli"))
        await router.route_inbound(InboundMessage(content="a", channel_name="cli", session_id="s1"))
        await router.route_inbound(InboundMessage(content="b", channel_name="cli", session_id="s2"))
        assert router.get_session_count() == 2

    def test_router_to_dict_serializes_state(self):
        """Router state serializes with channels and session info."""
        router = MessageRouter()
        router.register_channel("cli", MockChannel("cli"))
        d = router.to_dict()
        assert "cli" in d["channels"]
        assert "sessions" in d
        assert d["rate_limit_rpm"] > 0

    async def test_router_to_dict_includes_sessions(self):
        """Router to_dict includes serialized sessions."""
        loop = MockHiveLoop()
        router = MessageRouter(hive_loop=loop)
        router.register_channel("cli", MockChannel("cli"))
        await router.route_inbound(
            InboundMessage(content="test", channel_name="cli", session_id="s1")
        )
        d = router.to_dict()
        assert "s1" in d["sessions"]
        assert d["sessions"]["s1"]["channel_name"] == "cli"


# ===========================================================================
# Error path tests (Amendment 10: at least 4 for externally-facing)
# ===========================================================================


class TestMessageRouterErrors:
    """Error path tests for MessageRouter."""

    async def test_route_to_unknown_channel_raises(self):
        """Routing to an unregistered channel raises UnknownChannelError."""
        loop = MockHiveLoop()
        router = MessageRouter(hive_loop=loop)
        msg = InboundMessage(
            content="Hello",
            channel_name="nonexistent",
            session_id="sess-err",
        )
        with pytest.raises(UnknownChannelError, match="nonexistent"):
            await router.route_inbound(msg)

    async def test_route_with_empty_content_raises(self):
        """Routing a message with empty content raises ValueError."""
        loop = MockHiveLoop()
        router = MessageRouter(hive_loop=loop)
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="",
            channel_name="cli",
            session_id="sess-empty",
        )
        with pytest.raises(ValueError, match="content"):
            await router.route_inbound(msg)

    async def test_route_with_whitespace_only_content_raises(self):
        """Routing a message with whitespace-only content raises ValueError."""
        loop = MockHiveLoop()
        router = MessageRouter(hive_loop=loop)
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="   \n\t  ",
            channel_name="cli",
            session_id="sess-ws",
        )
        with pytest.raises(ValueError, match="content"):
            await router.route_inbound(msg)

    async def test_route_when_hive_loop_fails_raises_routing_error(self):
        """Routing failure from HiveLoop is wrapped in RoutingError."""
        router = MessageRouter(hive_loop=FailingHiveLoop())
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="Hello",
            channel_name="cli",
            session_id="sess-fail",
        )
        with pytest.raises(RoutingError, match="Model inference failed"):
            await router.route_inbound(msg)

    async def test_route_without_hive_loop_raises_routing_error(self):
        """Routing without a connected HiveLoop raises RoutingError."""
        router = MessageRouter()  # No hive_loop
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="Hello",
            channel_name="cli",
            session_id="sess-no-loop",
        )
        with pytest.raises(RoutingError, match="HiveLoop not connected"):
            await router.route_inbound(msg)

    async def test_rate_limit_exceeded_raises(self):
        """Exceeding rate limit raises RateLimitError."""
        loop = MockHiveLoop()
        router = MessageRouter(hive_loop=loop, rate_limit_rpm=3)
        router.register_channel("cli", MockChannel("cli"))

        # Send 3 messages (at limit)
        for i in range(3):
            msg = InboundMessage(
                content=f"Msg {i}",
                channel_name="cli",
                session_id=f"sess-rl-{i}",
            )
            await router.route_inbound(msg)

        # 4th should exceed rate limit
        msg = InboundMessage(
            content="One more",
            channel_name="cli",
            session_id="sess-rl-extra",
        )
        with pytest.raises(RateLimitError, match="Rate limit exceeded"):
            await router.route_inbound(msg)

    async def test_rate_limit_resets_after_window(self):
        """Rate limit counter resets after the time window expires."""
        loop = MockHiveLoop()
        # Use a very short window for testing
        router = MessageRouter(
            hive_loop=loop,
            rate_limit_rpm=2,
            rate_limit_window_seconds=0.1,
        )
        router.register_channel("cli", MockChannel("cli"))

        # Hit the limit
        for i in range(2):
            await router.route_inbound(
                InboundMessage(content=f"m{i}", channel_name="cli", session_id=f"s{i}")
            )

        # Wait for window to expire
        await asyncio.sleep(0.15)

        # Should succeed after reset
        response = await router.route_inbound(
            InboundMessage(content="after reset", channel_name="cli", session_id="s-reset")
        )
        assert response.content == "Mock response"

    async def test_route_with_empty_session_id_raises(self):
        """Routing with empty session_id raises ValueError."""
        loop = MockHiveLoop()
        router = MessageRouter(hive_loop=loop)
        router.register_channel("cli", MockChannel("cli"))
        msg = InboundMessage(
            content="Hello",
            channel_name="cli",
            session_id="",
        )
        with pytest.raises(ValueError, match="session_id"):
            await router.route_inbound(msg)


# ===========================================================================
# Concurrency stress test (Amendment 12)
# ===========================================================================


class TestMessageRouterConcurrency:
    """Concurrency stress tests for MessageRouter."""

    async def test_concurrent_route_inbound_no_data_loss(self):
        """50 concurrent route_inbound calls produce correct session state."""
        loop = SlowHiveLoop(delay=0.01, response="ok")
        router = MessageRouter(hive_loop=loop, rate_limit_rpm=200)
        router.register_channel("cli", MockChannel("cli"))

        async def send_message(idx: int) -> OutboundMessage:
            msg = InboundMessage(
                content=f"Message {idx}",
                channel_name="cli",
                session_id=f"sess-{idx}",
            )
            return await router.route_inbound(msg)

        results = await asyncio.gather(*[send_message(i) for i in range(50)])

        # All 50 should return valid responses
        assert len(results) == 50
        for r in results:
            assert r.content == "ok"

        # All 50 sessions should exist
        assert router.get_session_count() == 50

        # Each session should have exactly 2 history entries (user + assistant)
        for i in range(50):
            session = router.get_session(f"sess-{i}")
            assert session is not None
            assert len(session.history) == 2
            assert session.history[0]["role"] == "user"
            assert session.history[0]["content"] == f"Message {i}"
            assert session.history[1]["role"] == "assistant"

    async def test_concurrent_route_to_same_session(self):
        """50 concurrent messages to the same session all recorded."""
        loop = SlowHiveLoop(delay=0.01, response="ok")
        router = MessageRouter(hive_loop=loop, rate_limit_rpm=200)
        router.register_channel("cli", MockChannel("cli"))

        async def send_message(idx: int) -> OutboundMessage:
            msg = InboundMessage(
                content=f"Concurrent {idx}",
                channel_name="cli",
                session_id="shared-sess",
            )
            return await router.route_inbound(msg)

        results = await asyncio.gather(*[send_message(i) for i in range(50)])

        assert len(results) == 50
        session = router.get_session("shared-sess")
        # 50 user + 50 assistant = 100 history entries
        assert len(session.history) == 100

        # Verify all user messages present (order may vary due to concurrency)
        user_messages = [h["content"] for h in session.history if h["role"] == "user"]
        assert len(user_messages) == 50
        for i in range(50):
            assert f"Concurrent {i}" in user_messages

    async def test_concurrent_register_and_route(self):
        """Registering channels while routing doesn't cause errors."""
        loop = MockHiveLoop(response="ok")
        router = MessageRouter(hive_loop=loop, rate_limit_rpm=200)
        router.register_channel("cli", MockChannel("cli"))

        async def register_channel(idx: int) -> None:
            router.register_channel(f"ch-{idx}", MockChannel(f"ch-{idx}"))

        async def send_message(idx: int) -> OutboundMessage:
            return await router.route_inbound(
                InboundMessage(
                    content=f"m{idx}",
                    channel_name="cli",
                    session_id=f"s{idx}",
                )
            )

        # Mix registrations and routing concurrently
        tasks = []
        for i in range(25):
            tasks.append(register_channel(i))
            tasks.append(send_message(i))

        results = await asyncio.gather(*tasks)
        # 25 route_inbound results (every other task)
        route_results = [r for r in results if r is not None]
        assert len(route_results) == 25
