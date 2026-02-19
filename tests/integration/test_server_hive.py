"""Integration tests for HTTP server wired to HiveLoop.

Tests that the server correctly delegates to HiveLoop.think() for:
- POST /api/chat — sends message through HiveLoop
- GET  /api/state — returns HiveLoop's HiveState
- GET  /api/health — includes state version and adapter count
- GET  /ws/stream — WebSocket streaming through HiveLoop

Amendment 3: HTTP routes delegate to HiveLoop (via MessageRouter when available,
             direct HiveLoop.think() as fallback for this integration test).
Amendment 8: Specific exception types at every catch site.
Amendment 9: No trivial assertions — assert specific values, not isinstance.
Amendment 10: At least 4 error/edge-case tests for externally-facing HTTP server.
Amendment 11: Tests use public interface only (no private attribute access).
"""

from vecna.adapters.base import BaseAdapter, ModelConfig
from vecna.orchestrator.loop import HiveConfig, HiveLoop


class MockServerAdapter(BaseAdapter):
    """Mock adapter for server integration tests.

    Returns a canned response with a HIVE_UPDATE block so that
    HiveLoop.think() can parse facts and update state.
    """

    def __init__(self) -> None:
        config = ModelConfig(name="mock-srv", model_id="mock-srv-v1")
        super().__init__(config)

    async def generate(self, prompt: str) -> str:
        return (
            "Server response to your query.\n\n"
            "<HIVE_UPDATE>\n"
            "new_facts:\n"
            '  - content: "Server test fact"\n'
            "    confidence: 0.9\n"
            '    domain: "general"\n'
            "overall_confidence: 0.85\n"
            "</HIVE_UPDATE>"
        )

    def _get_provider_name(self) -> str:
        return "mock"


def _make_hive_loop() -> HiveLoop:
    """Build a minimal HiveLoop with a mock adapter for testing."""
    config = HiveConfig(
        use_pg_memory=False,
        use_semantic_memory=False,
        auto_execute_code=False,
        auto_execute_tools=False,
        enable_rewoo_planning=False,
        verbose=False,
        max_cycles=1,
    )
    loop = HiveLoop(
        config=config,
        adapters=[MockServerAdapter()],
        name="test-server",
    )
    return loop


class TestServerChatEndpoint:
    """Tests for POST /api/chat wired to HiveLoop."""

    async def test_chat_returns_200_with_response(self, aiohttp_client):
        """POST /api/chat returns 200 with a non-empty response from HiveLoop."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "Hello server"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "response" in data
        # Amendment 9: assert specific content, not just 'exists'
        assert "Server response" in data["response"]

    async def test_chat_updates_hive_state_version(self, aiohttp_client):
        """POST /api/chat causes HiveState version to advance."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        await client.post(
            "/api/chat",
            json={"message": "Add a fact"},
        )
        resp = await client.get("/api/state")
        data = await resp.json()
        # After one chat cycle, version must be >= 1
        assert data["version"] >= 1

    async def test_chat_malformed_json_returns_400(self, aiohttp_client):
        """Amendment 10: malformed input returns 400."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            data=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["error"] == "Invalid JSON"

    async def test_chat_empty_message_returns_400(self, aiohttp_client):
        """Amendment 10: empty message field returns 400."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": ""},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["error"] == "Message required"

    async def test_chat_missing_message_returns_400(self, aiohttp_client):
        """Amendment 10: missing message field returns 400."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"session_id": "test"},
        )
        assert resp.status == 400
        data = await resp.json()
        assert data["error"] == "Message required"

    async def test_chat_returns_state_version_in_response(self, aiohttp_client):
        """Response body includes state_version field."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "Hello server"},
        )
        data = await resp.json()
        assert "state_version" in data
        assert data["state_version"] >= 1


class TestServerStateEndpoint:
    """Tests for GET /api/state wired to HiveLoop."""

    async def test_state_returns_full_dict_with_facts_and_beliefs(self, aiohttp_client):
        """GET /api/state returns HiveState fields including facts, beliefs, version."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        resp = await client.get("/api/state")
        assert resp.status == 200
        data = await resp.json()
        # Amendment 9: assert specific fields exist and have correct types
        assert "version" in data
        assert "facts" in data
        assert "beliefs" in data
        assert isinstance(data["facts"], list)
        assert isinstance(data["beliefs"], list)

    async def test_state_reflects_hive_loop_state(self, aiohttp_client):
        """State endpoint returns the HiveLoop's actual state, not a separate one."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)

        # First get baseline state
        resp1 = await client.get("/api/state")
        data1 = await resp1.json()
        initial_version = data1["version"]

        # Do a chat to mutate state
        await client.post("/api/chat", json={"message": "hello"})

        # State should have advanced
        resp2 = await client.get("/api/state")
        data2 = await resp2.json()
        assert data2["version"] > initial_version


class TestServerWebSocket:
    """Tests for /ws/stream WebSocket endpoint wired to HiveLoop."""

    async def test_ws_stream_connects_and_returns_response(self, aiohttp_client):
        """WebSocket /ws/stream accepts connection and returns HiveLoop response."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        ws = await client.ws_connect("/ws/stream?token=test-token")
        await ws.send_json({"message": "ws test"})
        msg = await ws.receive_json()
        # Amendment 9: assert specific content in response
        assert "response" in msg
        assert "Server response" in msg["response"]
        await ws.close()

    async def test_ws_stream_invalid_json_returns_error(self, aiohttp_client):
        """Amendment 10: WebSocket with invalid JSON returns error."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        ws = await client.ws_connect("/ws/stream?token=test-token")
        await ws.send_str("not-json")
        msg = await ws.receive_json()
        assert msg["error"] == "Invalid JSON"
        await ws.close()

    async def test_ws_stream_empty_message_returns_error(self, aiohttp_client):
        """Amendment 10: WebSocket with empty message returns error."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        ws = await client.ws_connect("/ws/stream?token=test-token")
        await ws.send_json({"message": ""})
        msg = await ws.receive_json()
        assert msg["error"] == "message field required"
        await ws.close()


class TestServerHealthEndpoint:
    """Tests for GET /api/health wired to HiveLoop."""

    async def test_health_returns_ok_with_state_version(self, aiohttp_client):
        """GET /api/health returns status ok and state_version."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert "state_version" in data
        # Initial state version should be 0
        assert data["state_version"] == 0

    async def test_health_includes_adapter_count(self, aiohttp_client):
        """GET /api/health includes adapter_count reflecting HiveLoop adapters."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        data = await resp.json()
        assert "adapter_count" in data
        assert data["adapter_count"] == 1


class TestServerHiveLoopIntegration:
    """Tests for full server-to-HiveLoop integration."""

    async def test_hive_loop_injected_via_create_app(self, aiohttp_client):
        """create_app with adapters initializes a HiveLoop on the app."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockServerAdapter()], config=None)
        client = await aiohttp_client(app)
        # Health endpoint should report adapter count from injected loop
        resp = await client.get("/api/health")
        data = await resp.json()
        assert data["adapter_count"] == 1

    async def test_pre_built_hive_loop_accepted(self, aiohttp_client):
        """create_app accepts a pre-built HiveLoop instance."""
        from vecna.server.app import create_app

        loop = _make_hive_loop()
        app = create_app(hive_loop=loop)
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        data = await resp.json()
        assert data["adapter_count"] == 1
        assert data["state_version"] == 0

    async def test_no_adapters_chat_returns_500(self, aiohttp_client):
        """Amendment 10: resource exhaustion — no adapters causes internal error."""
        from vecna.server.app import create_app

        app = create_app(adapters=[], config=None)
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "Hello"},
        )
        # HiveLoop.think() raises ValueError when no adapters
        assert resp.status == 500
        data = await resp.json()
        assert "error" in data

    async def test_backward_compatible_create_app_no_args(self, aiohttp_client):
        """create_app() with no args should still work (backward compat)."""
        from vecna.server.app import create_app

        # When called with no args, should still create a valid app
        # but /api/chat won't have HiveLoop (placeholder behavior)
        app = create_app()
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        assert resp.status == 200
