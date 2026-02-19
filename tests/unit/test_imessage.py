"""Tests for the iMessage channel adapter via imsg CLI."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vecna.channels.imessage import (
    iMessageChannel,
    ImsgConfig,
    ImsgParseError,
)
from vecna.channels.base import (
    OutboundMessage,
    ChannelCapability,
)


class TestImsgConfig:
    def test_default_config(self):
        config = ImsgConfig()
        assert config.binary_path == "imsg"
        assert config.watch_timeout == 0  # 0 = indefinite
        assert config.privacy_tier == "local_only"
        assert config.max_message_length == 10000

    def test_custom_config(self):
        config = ImsgConfig(binary_path="/usr/local/bin/imsg", watch_timeout=60)
        assert config.binary_path == "/usr/local/bin/imsg"
        assert config.watch_timeout == 60


class TestiMessageChannelProperties:
    def test_channel_name(self):
        channel = iMessageChannel()
        assert channel.name == "imessage"

    def test_channel_capabilities(self):
        channel = iMessageChannel()
        caps = channel.capabilities
        assert ChannelCapability.TEXT in caps
        assert ChannelCapability.IMAGES in caps

    def test_channel_disabled_by_default(self):
        channel = iMessageChannel()
        assert channel.is_running is False

    def test_channel_privacy_tier(self):
        channel = iMessageChannel()
        assert channel.config.privacy_tier == "local_only"


class TestiMessageParsing:
    def test_parse_inbound_message(self):
        channel = iMessageChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "text": "Hey, what's up?",
                "date": "2026-02-16T10:30:00",
                "chat_id": "chat123",
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert msg.sender == "+1234567890"
        assert msg.content == "Hey, what's up?"
        assert msg.channel == "imessage"

    def test_parse_inbound_with_attachment(self):
        channel = iMessageChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "text": "Check this out",
                "attachments": [
                    {"filename": "photo.jpg", "mime_type": "image/jpeg"},
                ],
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert len(msg.attachments) == 1
        assert msg.attachments[0]["filename"] == "photo.jpg"

    def test_parse_inbound_skips_own_messages(self):
        channel = iMessageChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "text": "My own message",
                "is_from_me": True,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert msg is None

    def test_parse_inbound_invalid_json_raises(self):
        channel = iMessageChannel()
        with pytest.raises(ImsgParseError):
            channel.parse_inbound("not valid json {{{")

    def test_parse_inbound_missing_text_uses_empty(self):
        channel = iMessageChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert msg is not None
        assert msg.content == ""

    def test_parse_inbound_preserves_chat_id_in_metadata(self):
        channel = iMessageChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "text": "Hello",
                "chat_id": "chat_abc",
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert msg.metadata["chat_id"] == "chat_abc"
        assert msg.metadata["privacy_tier"] == "local_only"

    def test_parse_inbound_missing_sender_uses_unknown(self):
        channel = iMessageChannel()
        raw_json = json.dumps(
            {
                "text": "No sender here",
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert msg.sender == "unknown"
        assert msg.content == "No sender here"

    def test_parse_inbound_multiple_attachments(self):
        channel = iMessageChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "text": "Files",
                "attachments": [
                    {"filename": "a.jpg", "mime_type": "image/jpeg"},
                    {"filename": "b.png", "mime_type": "image/png"},
                    {"filename": "c.pdf", "mime_type": "application/pdf"},
                ],
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert len(msg.attachments) == 3
        assert msg.attachments[2]["filename"] == "c.pdf"


class TestiMessageSend:
    async def test_send_message(self):
        channel = iMessageChannel()
        msg = OutboundMessage(
            channel="imessage",
            recipient="+1234567890",
            content="Hello from Vecna!",
        )

        with patch(
            "vecna.channels.imessage.iMessageChannel._exec_imsg_send",
            new_callable=AsyncMock,
            return_value=(0, "Message sent", ""),
        ):
            success = await channel.send(msg)
            assert success is True

    async def test_send_message_failure(self):
        channel = iMessageChannel()
        msg = OutboundMessage(
            channel="imessage",
            recipient="+1234567890",
            content="Hello!",
        )

        with patch(
            "vecna.channels.imessage.iMessageChannel._exec_imsg_send",
            new_callable=AsyncMock,
            return_value=(1, "", "Failed to send"),
        ):
            success = await channel.send(msg)
            assert success is False

    async def test_send_truncates_long_messages(self):
        channel = iMessageChannel(config=ImsgConfig(max_message_length=50))
        msg = OutboundMessage(
            channel="imessage",
            recipient="+1234567890",
            content="A" * 100,
        )

        with patch(
            "vecna.channels.imessage.iMessageChannel._exec_imsg_send",
            new_callable=AsyncMock,
            return_value=(0, "Sent", ""),
        ) as mock_send:
            await channel.send(msg)
            # Verify the actual sent content was truncated
            call_args = mock_send.call_args
            sent_text = call_args[0][1]  # second positional arg is text
            assert len(sent_text) <= 50

    async def test_send_does_not_truncate_short_messages(self):
        channel = iMessageChannel(config=ImsgConfig(max_message_length=100))
        msg = OutboundMessage(
            channel="imessage",
            recipient="+1234567890",
            content="Short message",
        )

        with patch(
            "vecna.channels.imessage.iMessageChannel._exec_imsg_send",
            new_callable=AsyncMock,
            return_value=(0, "Sent", ""),
        ) as mock_send:
            await channel.send(msg)
            call_args = mock_send.call_args
            sent_text = call_args[0][1]
            assert sent_text == "Short message"


class TestiMessageStartStop:
    async def test_start_sets_running(self):
        channel = iMessageChannel()
        with patch(
            "vecna.channels.imessage.iMessageChannel._check_binary",
            return_value=True,
        ):
            # Don't actually start the watch process
            with patch.object(channel, "_start_watch_process", new_callable=AsyncMock):
                await channel.start()
                assert channel.is_running is True

    async def test_stop_clears_running(self):
        channel = iMessageChannel()
        # Simulate a started channel by using start with mocked binary
        with patch(
            "vecna.channels.imessage.iMessageChannel._check_binary",
            return_value=True,
        ):
            with patch.object(channel, "_start_watch_process", new_callable=AsyncMock):
                await channel.start()
                assert channel.is_running is True

        # Now mock the watch process for termination
        mock_proc = MagicMock()
        mock_proc.terminate = MagicMock()
        mock_proc.wait = AsyncMock()
        channel._watch_process = mock_proc

        await channel.stop()
        assert channel.is_running is False

    async def test_start_fails_without_binary(self):
        channel = iMessageChannel()
        with patch(
            "vecna.channels.imessage.iMessageChannel._check_binary",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="imsg"):
                await channel.start()

    async def test_start_stop_lifecycle(self):
        """Full start-stop cycle works without errors."""
        channel = iMessageChannel()
        with patch(
            "vecna.channels.imessage.iMessageChannel._check_binary",
            return_value=True,
        ):
            with patch.object(channel, "_start_watch_process", new_callable=AsyncMock):
                await channel.start()
                assert channel.is_running is True

        # Stop without a real process should still work
        channel._watch_process = None
        await channel.stop()
        assert channel.is_running is False
