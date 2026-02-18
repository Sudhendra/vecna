"""Tests for the HTTP server.

Tests cover all four API endpoints plus required error paths per Amendment 10:
- Malformed JSON input (400)
- Missing required fields (400)
- WebSocket auth failure (rejected)
- HiveLoop timeout handling (504)
"""

import asyncio
from unittest.mock import patch

from aiohttp import web
from click.testing import CliRunner

from vecna.server.app import create_app


class TestHealthEndpoint:
    """Tests for GET /api/health."""

    async def test_health_returns_ok_status_and_version(self, aiohttp_client):
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data
        # Verify timestamp is ISO format (parseable)
        from datetime import datetime

        datetime.fromisoformat(data["timestamp"])


class TestChatEndpoint:
    """Tests for POST /api/chat."""

    async def test_chat_returns_response_with_message_and_session(self, aiohttp_client):
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "Hello Vecna", "session_id": "test-session-42"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "response" in data
        assert data["session_id"] == "test-session-42"
        assert "Hello Vecna" in data["response"]
        # Verify timestamp is present and parseable
        from datetime import datetime

        datetime.fromisoformat(data["timestamp"])

    async def test_chat_uses_default_session_when_omitted(self, aiohttp_client):
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "Hello"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["session_id"] == "default"

    async def test_chat_malformed_json_returns_400(self, aiohttp_client):
        """Amendment 10: malformed input error path."""
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            data=b"this is not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["error"] == "Invalid JSON"

    async def test_chat_missing_message_field_returns_400(self, aiohttp_client):
        """Amendment 10: missing required field error path."""
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"session_id": "test"},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["error"] == "Message required"

    async def test_chat_empty_message_returns_400(self, aiohttp_client):
        """Empty string message should also be rejected."""
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "", "session_id": "test"},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["error"] == "Message required"

    async def test_chat_whitespace_only_message_returns_400(self, aiohttp_client):
        """Whitespace-only message should be rejected."""
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "   ", "session_id": "test"},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["error"] == "Message required"

    async def test_chat_timeout_returns_504(self, aiohttp_client):
        """Amendment 10: timeout/connection error path.

        When the router (or future HiveLoop) times out, return 504 Gateway Timeout.
        We simulate this by injecting a router that raises asyncio.TimeoutError.
        """
        app = create_app()

        # Inject a mock router that raises TimeoutError
        async def timeout_router(message: str, session_id: str):
            raise asyncio.TimeoutError("HiveLoop.think() timed out")

        app["message_router"] = timeout_router
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "Hello", "session_id": "test"},
        )
        assert resp.status == 504
        data = await resp.json()
        assert data["error"] == "Request timed out"


class TestStateEndpoint:
    """Tests for GET /api/state."""

    async def test_state_returns_version_and_summary_fields(self, aiohttp_client):
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.get("/api/state")
        assert resp.status == 200
        data = await resp.json()
        assert data["version"] == 0
        assert data["num_facts"] == 0
        assert data["num_beliefs"] == 0
        assert data["num_hypotheses"] == 0
        assert data["num_goals"] == 0
        assert data["num_open_questions"] == 0
        assert data["num_contradictions"] == 0

    async def test_state_lazy_initializes_hive_state(self, aiohttp_client):
        """First call should create a HiveState; second should reuse it."""
        app = create_app()
        assert app["hive_state"] is None
        client = await aiohttp_client(app)

        resp1 = await client.get("/api/state")
        assert resp1.status == 200
        data1 = await resp1.json()

        # Second call should return same state (same version, consistent)
        resp2 = await client.get("/api/state")
        assert resp2.status == 200
        data2 = await resp2.json()
        assert data1["version"] == data2["version"]
        assert data1["updated_at"] == data2["updated_at"]


class TestWebhookEndpoint:
    """Tests for POST /api/webhooks/ingest."""

    async def test_webhook_accepts_valid_event(self, aiohttp_client):
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/webhooks/ingest",
            json={
                "source": "github",
                "event": "push",
                "payload": {"repo": "test/repo"},
            },
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "accepted"
        assert data["source"] == "github"
        assert data["event"] == "push"

    async def test_webhook_malformed_json_returns_400(self, aiohttp_client):
        """Amendment 10: malformed input on webhook endpoint."""
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/webhooks/ingest",
            data=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["error"] == "Invalid JSON"

    async def test_webhook_defaults_unknown_source_and_event(self, aiohttp_client):
        """When source/event not provided, defaults to 'unknown'."""
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/webhooks/ingest",
            json={"payload": {"data": "test"}},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["source"] == "unknown"
        assert data["event"] == "unknown"


class TestWebSocketAuth:
    """Tests for WebSocket /ws/stream authentication."""

    async def test_websocket_rejects_unauthenticated_connection(self, aiohttp_client):
        """Amendment 10: authentication failure error path.

        WebSocket connections without a valid token should be rejected.
        """
        app = create_app()
        client = await aiohttp_client(app)
        # Attempt WebSocket connection without auth token
        async with client.ws_connect("/ws/stream", autoping=False) as ws:
            msg = await ws.receive()
            # Server should close the connection with an error
            assert msg.type in (
                web.WSMsgType.CLOSE,
                web.WSMsgType.ERROR,
                web.WSMsgType.CLOSING,
            )


class TestRouteRegistration:
    """Tests that routes are properly registered."""

    async def test_unknown_route_returns_404(self, aiohttp_client):
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.get("/api/nonexistent")
        assert resp.status == 404

    async def test_chat_get_method_not_allowed(self, aiohttp_client):
        """GET on POST-only endpoint should return 405."""
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.get("/api/chat")
        assert resp.status == 405

    async def test_health_post_method_not_allowed(self, aiohttp_client):
        """POST on GET-only endpoint should return 405."""
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.post("/api/health", json={})
        assert resp.status == 405


class TestCreateApp:
    """Tests for the create_app factory function."""

    def test_create_app_returns_application_with_expected_keys(self):
        app = create_app()
        assert app["hive_state"] is None
        assert app["sessions"] == {}
        assert app["message_router"] is None

    def test_create_app_stores_host_and_port(self):
        app = create_app(host="0.0.0.0", port=9999)
        assert app["host"] == "0.0.0.0"
        assert app["port"] == 9999

    def test_create_app_default_host_and_port(self):
        app = create_app()
        assert app["host"] == "127.0.0.1"
        assert app["port"] == 8420


class TestServeCliCommand:
    """Tests for the 'vecna serve' CLI command."""

    def test_serve_command_exists_in_help(self):
        from vecna.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "serve" in result.output

    def test_serve_command_has_host_and_port_options(self):
        from vecna.cli.main import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["serve", "--help"])
        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output
        assert "8420" in result.output

    def test_serve_command_calls_run_server(self):
        from vecna.cli.main import cli

        runner = CliRunner()
        with patch("vecna.server.app.run_server") as mock_run:
            result = runner.invoke(cli, ["serve", "--host", "0.0.0.0", "--port", "9999"])
            assert result.exit_code == 0
            mock_run.assert_called_once_with(host="0.0.0.0", port=9999)
