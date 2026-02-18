"""Tests for the WhatsApp channel adapter via wacli CLI."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vecna.channels.whatsapp import (
    WhatsAppChannel,
    WacliConfig,
    WacliResult,
    WacliParseError,
)
from vecna.channels.base import (
    OutboundMessage,
    ChannelCapability,
)


class TestWacliConfig:
    def test_default_config(self):
        config = WacliConfig()
        assert config.binary_path == "wacli"
        assert config.privacy_tier == "local_only"
        assert config.max_message_length == 65536
        assert config.search_limit == 50

    def test_custom_config(self):
        config = WacliConfig(binary_path="/usr/local/bin/wacli", search_limit=20)
        assert config.binary_path == "/usr/local/bin/wacli"
        assert config.search_limit == 20


class TestWhatsAppChannelProperties:
    def test_channel_name(self):
        channel = WhatsAppChannel()
        assert channel.name == "whatsapp"

    def test_channel_capabilities(self):
        channel = WhatsAppChannel()
        caps = channel.capabilities
        assert ChannelCapability.TEXT in caps
        assert ChannelCapability.IMAGES in caps

    def test_channel_not_running_initially(self):
        channel = WhatsAppChannel()
        assert channel.is_running is False

    def test_channel_privacy_tier(self):
        channel = WhatsAppChannel()
        assert channel.config.privacy_tier == "local_only"


class TestWhatsAppParsing:
    def test_parse_inbound_message(self):
        channel = WhatsAppChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "sender_name": "Alice",
                "text": "Hello from WhatsApp",
                "timestamp": "2026-02-16T10:30:00",
                "chat_id": "chat_abc",
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert msg.sender == "+1234567890"
        assert msg.content == "Hello from WhatsApp"
        assert msg.channel == "whatsapp"

    def test_parse_inbound_with_media(self):
        channel = WhatsAppChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "text": "Check this photo",
                "media": [
                    {"type": "image", "filename": "photo.jpg", "mime": "image/jpeg"},
                ],
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert len(msg.attachments) == 1
        assert msg.attachments[0]["type"] == "image"
        assert msg.attachments[0]["filename"] == "photo.jpg"

    def test_parse_inbound_skips_own_messages(self):
        channel = WhatsAppChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "text": "My outgoing msg",
                "is_from_me": True,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert msg is None

    def test_parse_inbound_invalid_json_raises(self):
        channel = WhatsAppChannel()
        with pytest.raises(WacliParseError, match="Invalid JSON"):
            channel.parse_inbound("{{invalid json}}")

    def test_parse_inbound_includes_sender_name_in_metadata(self):
        channel = WhatsAppChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "sender_name": "Bob",
                "text": "Hey",
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert msg.metadata["sender_name"] == "Bob"

    def test_parse_inbound_missing_text_uses_empty(self):
        channel = WhatsAppChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert msg.content == ""

    def test_parse_inbound_missing_sender_uses_unknown(self):
        channel = WhatsAppChannel()
        raw_json = json.dumps(
            {
                "text": "No sender here",
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert msg.sender == "unknown"
        assert msg.content == "No sender here"

    def test_parse_inbound_preserves_chat_id_in_metadata(self):
        channel = WhatsAppChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "text": "Hello",
                "chat_id": "chat_xyz",
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert msg.metadata["chat_id"] == "chat_xyz"
        assert msg.metadata["privacy_tier"] == "local_only"

    def test_parse_inbound_multiple_media_attachments(self):
        channel = WhatsAppChannel()
        raw_json = json.dumps(
            {
                "sender": "+1234567890",
                "text": "Files",
                "media": [
                    {"type": "image", "filename": "a.jpg", "mime": "image/jpeg"},
                    {"type": "image", "filename": "b.png", "mime": "image/png"},
                    {"type": "document", "filename": "c.pdf", "mime": "application/pdf"},
                ],
                "is_from_me": False,
            }
        )
        msg = channel.parse_inbound(raw_json)
        assert len(msg.attachments) == 3
        assert msg.attachments[2]["filename"] == "c.pdf"


class TestWhatsAppSend:
    async def test_send_message(self):
        channel = WhatsAppChannel()
        msg = OutboundMessage(
            channel="whatsapp",
            recipient="+1234567890",
            content="Hello from Vecna!",
        )

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(0, "Message sent", ""),
        ):
            success = await channel.send(msg)
            assert success is True

    async def test_send_message_failure(self):
        channel = WhatsAppChannel()
        msg = OutboundMessage(
            channel="whatsapp",
            recipient="+1234567890",
            content="Hello!",
        )

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(1, "", "Not connected"),
        ):
            success = await channel.send(msg)
            assert success is False

    async def test_send_truncates_long_messages(self):
        channel = WhatsAppChannel(config=WacliConfig(max_message_length=50))
        msg = OutboundMessage(
            channel="whatsapp",
            recipient="+1234567890",
            content="B" * 100,
        )

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(0, "Sent", ""),
        ) as mock_exec:
            await channel.send(msg)
            # _exec_wacli is called with ("send", recipient, content)
            call_args = mock_exec.call_args[0]
            sent_content = call_args[2]  # third positional arg is content
            assert len(sent_content) == 50

    async def test_send_does_not_truncate_short_messages(self):
        channel = WhatsAppChannel(config=WacliConfig(max_message_length=100))
        msg = OutboundMessage(
            channel="whatsapp",
            recipient="+1234567890",
            content="Short message",
        )

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(0, "Sent", ""),
        ) as mock_exec:
            await channel.send(msg)
            call_args = mock_exec.call_args[0]
            sent_content = call_args[2]
            assert sent_content == "Short message"


class TestWhatsAppSearch:
    async def test_search_messages(self):
        channel = WhatsAppChannel()
        mock_output = json.dumps(
            [
                {
                    "sender": "+111",
                    "text": "Meeting tomorrow",
                    "timestamp": "2026-02-15T09:00:00",
                },
                {
                    "sender": "+222",
                    "text": "Meeting agenda",
                    "timestamp": "2026-02-15T10:00:00",
                },
            ]
        )

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await channel.search("meeting", limit=10)
            assert result.success is True
            assert len(result.data) == 2
            assert result.data[0]["text"] == "Meeting tomorrow"
            assert result.command == "search"

    async def test_search_handles_error(self):
        channel = WhatsAppChannel()

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(1, "", "Database locked"),
        ):
            result = await channel.search("test")
            assert result.success is False
            assert "locked" in result.error.lower()

    async def test_search_handles_invalid_json_output(self):
        channel = WhatsAppChannel()

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(0, "not valid json {{", ""),
        ):
            result = await channel.search("test")
            assert result.success is False
            assert "parse" in result.error.lower()

    async def test_search_uses_default_limit(self):
        channel = WhatsAppChannel(config=WacliConfig(search_limit=25))

        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._exec_wacli",
            new_callable=AsyncMock,
            return_value=(0, "[]", ""),
        ) as mock_exec:
            await channel.search("query")
            call_args = mock_exec.call_args[0]
            # Should include --limit=25 in args
            assert "--limit=25" in call_args


class TestWhatsAppStartStop:
    async def test_start_sets_running(self):
        channel = WhatsAppChannel()
        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._check_binary",
            return_value=True,
        ):
            with patch.object(channel, "_start_watch_process", new_callable=AsyncMock):
                await channel.start()
                assert channel.is_running is True

    async def test_stop_clears_running(self):
        channel = WhatsAppChannel()
        # Simulate a started channel
        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._check_binary",
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
        channel = WhatsAppChannel()
        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._check_binary",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="wacli"):
                await channel.start()

    async def test_start_stop_lifecycle(self):
        """Full start-stop cycle works without errors."""
        channel = WhatsAppChannel()
        with patch(
            "vecna.channels.whatsapp.WhatsAppChannel._check_binary",
            return_value=True,
        ):
            with patch.object(channel, "_start_watch_process", new_callable=AsyncMock):
                await channel.start()
                assert channel.is_running is True

        # Stop without a real process should still work
        channel._watch_process = None
        await channel.stop()
        assert channel.is_running is False


class TestWacliResult:
    def test_success_result(self):
        result = WacliResult(
            success=True,
            command="search",
            data=[{"text": "hello"}],
        )
        assert result.success is True
        assert result.command == "search"
        assert result.data[0]["text"] == "hello"

    def test_error_result(self):
        result = WacliResult(
            success=False,
            command="search",
            error="not authenticated",
        )
        assert result.success is False
        assert result.error == "not authenticated"

    def test_to_dict_via_serializable_mixin(self):
        """Amendment 7: to_dict() comes from SerializableMixin, not custom method."""
        result = WacliResult(success=True, command="send", data=[])
        d = result.to_dict()
        assert d["success"] is True
        assert d["command"] == "send"
        assert d["data"] == []
        assert d["error"] == ""
        assert d["raw_output"] == ""

    def test_default_result_values(self):
        result = WacliResult()
        assert result.success is False
        assert result.command == ""
        assert result.data == []
        assert result.error == ""
        assert result.raw_output == ""
