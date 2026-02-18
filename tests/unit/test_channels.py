"""
Tests for the channel adapter system.

Tests:
- InboundMessage creation and fields
- OutboundMessage creation and fields
- ChannelCapability enum
- CLIChannel capabilities and behavior
- BaseChannel ABC enforcement
- Error/edge-case tests (Amendment 10)
- Concurrency tests (Amendment 12)
"""

import asyncio
from datetime import datetime

from vecna.channels.base import (
    BaseChannel,
    InboundMessage,
    OutboundMessage,
    ChannelCapability,
)


class TestInboundMessage:
    """Tests for InboundMessage dataclass."""

    def test_text_message(self):
        msg = InboundMessage(
            channel="cli",
            sender="user",
            content="Hello Vecna",
        )
        assert msg.channel == "cli"
        assert msg.content == "Hello Vecna"
        assert msg.sender == "user"
        assert msg.message_type == "text"

    def test_message_with_attachments(self):
        msg = InboundMessage(
            channel="imessage",
            sender="user",
            content="Check this",
            attachments=[{"type": "image", "url": "/path/to/img.png"}],
        )
        assert len(msg.attachments) == 1
        assert msg.attachments[0]["type"] == "image"
        assert msg.attachments[0]["url"] == "/path/to/img.png"

    def test_message_id_is_unique(self):
        msg1 = InboundMessage(channel="cli", sender="user", content="one")
        msg2 = InboundMessage(channel="cli", sender="user", content="two")
        assert msg1.message_id != msg2.message_id

    def test_timestamp_is_set(self):
        before = datetime.now()
        msg = InboundMessage(channel="cli", sender="user", content="test")
        after = datetime.now()
        assert before <= msg.timestamp <= after

    def test_reply_to_defaults_to_none(self):
        msg = InboundMessage(channel="cli", sender="user", content="test")
        assert msg.reply_to is None

    def test_reply_to_threaded_message(self):
        msg = InboundMessage(
            channel="slack",
            sender="user",
            content="Reply",
            reply_to="parent-msg-id",
        )
        assert msg.reply_to == "parent-msg-id"

    def test_metadata_defaults_to_empty_dict(self):
        msg = InboundMessage(channel="cli", sender="user", content="test")
        assert msg.metadata == {}

    def test_metadata_with_custom_fields(self):
        msg = InboundMessage(
            channel="slack",
            sender="user",
            content="test",
            metadata={"thread_ts": "12345", "workspace": "vecna-team"},
        )
        assert msg.metadata["thread_ts"] == "12345"
        assert msg.metadata["workspace"] == "vecna-team"

    def test_empty_content_is_allowed(self):
        """Channels like iMessage can send attachment-only messages."""
        msg = InboundMessage(
            channel="imessage",
            sender="user",
            content="",
            attachments=[{"type": "image", "url": "/path.png"}],
        )
        assert msg.content == ""
        assert len(msg.attachments) == 1


class TestOutboundMessage:
    """Tests for OutboundMessage dataclass."""

    def test_text_response(self):
        msg = OutboundMessage(
            channel="cli",
            recipient="user",
            content="Hello, I am Vecna.",
        )
        assert msg.content == "Hello, I am Vecna."
        assert msg.channel == "cli"
        assert msg.recipient == "user"

    def test_outbound_defaults(self):
        msg = OutboundMessage(
            channel="cli",
            recipient="user",
            content="response",
        )
        assert msg.message_type == "text"
        assert msg.attachments == []
        assert msg.metadata == {}
        assert msg.reply_to is None

    def test_outbound_with_attachments(self):
        msg = OutboundMessage(
            channel="slack",
            recipient="user",
            content="Here's the file",
            attachments=[{"type": "file", "path": "/tmp/report.pdf"}],
        )
        assert msg.attachments[0]["path"] == "/tmp/report.pdf"

    def test_outbound_reply_to(self):
        msg = OutboundMessage(
            channel="slack",
            recipient="user",
            content="Threaded reply",
            reply_to="parent-id",
        )
        assert msg.reply_to == "parent-id"


class TestChannelCapability:
    """Tests for ChannelCapability enum."""

    def test_all_capabilities_have_string_values(self):
        for cap in ChannelCapability:
            assert cap.value == cap.value.lower()

    def test_capability_values(self):
        assert ChannelCapability.TEXT.value == "text"
        assert ChannelCapability.STREAMING.value == "streaming"
        assert ChannelCapability.IMAGES.value == "images"
        assert ChannelCapability.RICH_TEXT.value == "rich_text"

    def test_capabilities_are_distinct(self):
        values = [cap.value for cap in ChannelCapability]
        assert len(values) == len(set(values))


class TestCLIChannel:
    """Tests for CLIChannel implementation."""

    def test_cli_capabilities(self):
        from vecna.channels.cli_channel import CLIChannel

        channel = CLIChannel()
        caps = channel.capabilities
        assert ChannelCapability.TEXT in caps
        assert ChannelCapability.STREAMING in caps
        assert ChannelCapability.RICH_TEXT in caps

    def test_cli_name(self):
        from vecna.channels.cli_channel import CLIChannel

        channel = CLIChannel()
        assert channel.name == "cli"

    async def test_cli_send_returns_true(self):
        from vecna.channels.cli_channel import CLIChannel

        channel = CLIChannel()
        msg = OutboundMessage(channel="cli", recipient="user", content="test output")
        result = await channel.send(msg)
        assert result is True

    async def test_cli_start_and_stop_are_safe(self):
        """Start and stop should not raise."""
        from vecna.channels.cli_channel import CLIChannel

        channel = CLIChannel()
        await channel.start()
        await channel.stop()
        # If we get here without exception, the test passes
        # But we also verify the channel is still usable after stop/start cycle
        result = await channel.send(
            OutboundMessage(channel="cli", recipient="user", content="after restart")
        )
        assert result is True


class TestBaseChannelABC:
    """Tests that BaseChannel enforces the ABC contract."""

    def test_cannot_instantiate_base_channel(self):
        """BaseChannel is abstract — direct instantiation must raise TypeError."""
        try:
            BaseChannel()  # type: ignore[abstract]
            assert False, "Should have raised TypeError"
        except TypeError as exc:
            assert "abstract" in str(exc).lower()

    def test_incomplete_implementation_raises(self):
        """A subclass missing abstract methods cannot be instantiated."""

        class PartialChannel(BaseChannel):
            name = "partial"
            capabilities = [ChannelCapability.TEXT]

            async def send(self, message: OutboundMessage) -> bool:
                return True

            # Missing: receive, start, stop

        try:
            PartialChannel()
            assert False, "Should have raised TypeError for missing abstract methods"
        except TypeError as exc:
            assert "abstract" in str(exc).lower()

    def test_complete_implementation_works(self):
        """A subclass implementing all methods can be instantiated."""
        from vecna.channels.cli_channel import CLIChannel

        channel = CLIChannel()
        assert channel.name == "cli"


class TestChannelEdgeCases:
    """Error and edge-case tests (Amendment 10)."""

    def test_inbound_message_very_long_content(self):
        """Messages with very long content should be handled without error."""
        long_content = "x" * 100_000
        msg = InboundMessage(channel="cli", sender="user", content=long_content)
        assert len(msg.content) == 100_000
        assert msg.content == long_content

    def test_inbound_message_unicode_content(self):
        """Messages with unicode characters should preserve content exactly."""
        unicode_content = "Hello \U0001f600 \u00e9\u00e0\u00fc \u4f60\u597d \U0001f30d"
        msg = InboundMessage(channel="cli", sender="user", content=unicode_content)
        assert msg.content == unicode_content

    def test_inbound_message_with_many_attachments(self):
        """Messages with many attachments should not lose any."""
        attachments = [{"type": "image", "url": f"/img_{i}.png"} for i in range(50)]
        msg = InboundMessage(
            channel="slack", sender="user", content="batch", attachments=attachments
        )
        assert len(msg.attachments) == 50
        assert msg.attachments[49]["url"] == "/img_49.png"

    def test_outbound_message_empty_content(self):
        """Outbound messages can have empty content (e.g. reaction-only)."""
        msg = OutboundMessage(channel="slack", recipient="user", content="")
        assert msg.content == ""

    def test_multiple_channels_have_isolated_defaults(self):
        """Default mutable fields should not be shared across instances."""
        msg1 = InboundMessage(channel="cli", sender="user", content="one")
        msg2 = InboundMessage(channel="cli", sender="user", content="two")
        msg1.attachments.append({"type": "file", "url": "/only_in_msg1.txt"})
        assert len(msg1.attachments) == 1
        assert len(msg2.attachments) == 0

    def test_inbound_message_special_characters_in_sender(self):
        """Sender field with special characters should be preserved."""
        msg = InboundMessage(channel="slack", sender="user@domain.com/+1-555-0100", content="hi")
        assert msg.sender == "user@domain.com/+1-555-0100"


class TestChannelConcurrency:
    """Concurrency tests for channel operations (Amendment 12)."""

    async def test_concurrent_cli_sends(self):
        """50+ concurrent sends should all succeed without data loss."""
        from vecna.channels.cli_channel import CLIChannel

        channel = CLIChannel()
        num_sends = 50

        async def send_one(i: int) -> bool:
            msg = OutboundMessage(channel="cli", recipient="user", content=f"message-{i}")
            return await channel.send(msg)

        results = await asyncio.gather(*[send_one(i) for i in range(num_sends)])
        assert len(results) == num_sends
        assert all(r is True for r in results)

    async def test_concurrent_inbound_message_creation(self):
        """50+ concurrent InboundMessage creations produce unique IDs."""
        num_messages = 50

        async def create_one(i: int) -> InboundMessage:
            return InboundMessage(channel="cli", sender="user", content=f"msg-{i}")

        messages = await asyncio.gather(*[create_one(i) for i in range(num_messages)])
        ids = [m.message_id for m in messages]
        assert len(set(ids)) == num_messages

    async def test_concurrent_start_stop(self):
        """Concurrent start/stop should not raise or corrupt state."""
        from vecna.channels.cli_channel import CLIChannel

        channel = CLIChannel()

        async def start_stop_cycle(i: int) -> bool:
            await channel.start()
            await channel.stop()
            return True

        results = await asyncio.gather(*[start_stop_cycle(i) for i in range(50)])
        assert len(results) == 50
        assert all(r is True for r in results)
