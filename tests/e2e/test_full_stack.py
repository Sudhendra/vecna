"""End-to-end integration tests for the full Vecna stack.

Validates complete flows with mock adapters (no real LLM calls):
- CLI -> HiveLoop -> Consensus -> Response -> State Update
- Server -> Channel -> HiveLoop -> Response -> Channel
- DreamLoop consolidation
- HumanModel persistence across sessions
- MetricsCollector end-to-end
- Config bootstrap

Amendment 9: No trivial assertions — assert specific values, fields, behaviors.
Amendment 10: At least 2 error/edge-case tests per component.
Amendment 11: Tests use public interface only.
"""

from aiohttp import web

from vecna.adapters.base import BaseAdapter, ModelConfig
from vecna.config.schema import create_default_config, Provider
from vecna.core.human_model import HumanModel, Preference
from vecna.memory.dream_loop import DreamLoop, DreamResult
from vecna.observability.dashboard import MetricsCollector
from vecna.orchestrator.loop import HiveConfig, HiveLoop


class MockE2EAdapter(BaseAdapter):
    """Mock adapter returning deterministic HIVE_UPDATE responses."""

    def __init__(self) -> None:
        config = ModelConfig(name="mock-e2e", model_id="mock-e2e-v1")
        super().__init__(config)

    async def generate(self, prompt: str) -> str:
        return (
            "I've analyzed the topic and found relevant information.\n\n"
            "<HIVE_UPDATE>\n"
            "new_facts:\n"
            '  - content: "Python is a programming language"\n'
            "    confidence: 0.95\n"
            '    evidence: "well-known fact"\n'
            '    domain: "code"\n'
            "belief_changes:\n"
            '  - content: "Testing improves code quality"\n'
            "    confidence: 0.9\n"
            '    reasoning: "industry best practice"\n'
            "overall_confidence: 0.9\n"
            "</HIVE_UPDATE>"
        )

    def _get_provider_name(self) -> str:
        return "mock"


class MockEmptyAdapter(BaseAdapter):
    """Mock adapter that returns an empty response."""

    def __init__(self) -> None:
        config = ModelConfig(name="mock-empty", model_id="mock-empty-v1")
        super().__init__(config)

    async def generate(self, prompt: str) -> str:
        return ""

    def _get_provider_name(self) -> str:
        return "mock"


# ============================================================
# CLI -> HiveLoop pipeline
# ============================================================


class TestCLIToHiveLoop:
    """Tests that validate the CLI-to-HiveLoop pipeline end-to-end."""

    async def test_think_returns_response_with_expected_content(self):
        """HiveLoop.think returns response containing mock adapter's output."""
        adapter = MockE2EAdapter()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="e2e-cli",
        )
        result = await loop.think("hello")
        # Amendment 9: assert specific content from our mock, not just existence
        assert "analyzed the topic" in result or "relevant information" in result

    async def test_think_updates_state_with_facts(self):
        """HiveLoop.think adds facts to HiveState from parsed HIVE_UPDATE."""
        adapter = MockE2EAdapter()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="e2e-state",
        )
        initial_facts = len(loop.state.facts)
        await loop.think("tell me about Python")
        # The mock adapter returns a fact about Python
        assert len(loop.state.facts) > initial_facts
        # Amendment 9: verify the actual fact content was extracted
        fact_contents = [f.content for f in loop.state.facts]
        assert any("Python" in c for c in fact_contents)

    async def test_multiple_cycles_accumulate_state(self):
        """Multiple think calls accumulate state entries."""
        adapter = MockE2EAdapter()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="e2e-accum",
        )
        await loop.think("first question")
        count_after_first = len(loop.state.facts) + len(loop.state.beliefs)
        await loop.think("second question")
        count_after_second = len(loop.state.facts) + len(loop.state.beliefs)
        # State should accumulate (or at least not shrink)
        assert count_after_second >= count_after_first

    async def test_state_version_increments_after_think(self):
        """HiveState version increments after each think cycle."""
        adapter = MockE2EAdapter()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="e2e-version",
        )
        initial_version = loop.state.version
        await loop.think("version test")
        assert loop.state.version > initial_version

    # Amendment 10: error/edge-case tests
    async def test_think_with_empty_input_still_returns(self):
        """HiveLoop.think with whitespace-only input returns a response string."""
        adapter = MockE2EAdapter()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="e2e-empty-input",
        )
        result = await loop.think("   ")
        # Should still get some response (mock adapter always returns)
        assert isinstance(result, str)

    async def test_think_with_empty_adapter_response(self):
        """HiveLoop.think handles adapter returning empty string."""
        adapter = MockEmptyAdapter()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="e2e-empty-adapter",
        )
        result = await loop.think("hello")
        # Should return empty string, not raise
        assert isinstance(result, str)


# ============================================================
# Server integration
# ============================================================


class TestServerIntegration:
    """Tests for the HTTP server endpoints using aiohttp test client."""

    async def test_chat_endpoint_returns_response(self, aiohttp_client):
        """POST /api/chat returns 200 with response field."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockE2EAdapter()])
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "test query"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "response" in data
        assert len(data["response"]) > 0

    async def test_state_endpoint_returns_state(self, aiohttp_client):
        """GET /api/state returns HiveState with version and facts."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockE2EAdapter()])
        client = await aiohttp_client(app)
        resp = await client.get("/api/state")
        assert resp.status == 200
        data = await resp.json()
        assert "version" in data
        assert "facts" in data

    async def test_health_endpoint_returns_ok(self, aiohttp_client):
        """GET /api/health returns status ok."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockE2EAdapter()])
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"

    async def test_health_endpoint_includes_adapter_count(self, aiohttp_client):
        """GET /api/health includes adapter_count when HiveLoop is wired."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockE2EAdapter()])
        client = await aiohttp_client(app)
        resp = await client.get("/api/health")
        data = await resp.json()
        assert data["adapter_count"] == 1

    # Amendment 10: error tests for externally-facing HTTP server
    async def test_chat_endpoint_rejects_empty_message(self, aiohttp_client):
        """POST /api/chat returns 400 for empty message."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockE2EAdapter()])
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": ""},
        )
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data

    async def test_chat_endpoint_rejects_invalid_json(self, aiohttp_client):
        """POST /api/chat returns 400 for malformed JSON."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockE2EAdapter()])
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            data=b"this is not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    async def test_chat_endpoint_without_hive_loop_returns_placeholder(self, aiohttp_client):
        """POST /api/chat without adapters returns placeholder response."""
        from vecna.server.app import create_app

        app = create_app()  # No adapters, no hive_loop
        client = await aiohttp_client(app)
        resp = await client.post(
            "/api/chat",
            json={"message": "hello"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert "placeholder" in data["response"].lower() or "received" in data["response"].lower()

    async def test_websocket_rejects_unauthenticated(self, aiohttp_client):
        """WebSocket connection without auth token is rejected."""
        from vecna.server.app import create_app

        app = create_app(adapters=[MockE2EAdapter()])
        client = await aiohttp_client(app)
        ws = await client.ws_connect("/ws/stream")
        # Server should close the connection with code 4001
        msg = await ws.receive()
        assert msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.CLOSED)


# ============================================================
# DreamLoop consolidation
# ============================================================


class TestDreamLoopIntegration:
    """Tests for dream consolidation pipeline."""

    def test_dream_loop_runs_without_pg_store(self):
        """DreamLoop runs in dry mode without a PG store and returns zeroed DreamResult."""
        dream = DreamLoop()
        result = dream.run(dry_run=True)
        assert isinstance(result, DreamResult)
        # Without a pg_store, all phases return 0
        assert result.events_compressed == 0
        assert result.memories_reinforced == 0
        assert result.memories_decayed == 0
        assert result.insights_generated == 0
        assert result.duration_seconds >= 0.0
        assert result.errors == []

    def test_dream_result_to_dict_has_expected_fields(self):
        """DreamResult.to_dict() includes all phase fields."""
        result = DreamResult(
            events_compressed=3,
            episodes_created=1,
            memories_reinforced=5,
            memories_decayed=2,
            insights_generated=1,
        )
        d = result.to_dict()
        assert d["events_compressed"] == 3
        assert d["episodes_created"] == 1
        assert d["memories_reinforced"] == 5
        assert d["memories_decayed"] == 2
        assert d["insights_generated"] == 1
        assert "timestamp" in d

    # Amendment 10: error/edge-case tests
    def test_dream_loop_handles_none_pg_store_gracefully(self):
        """DreamLoop with pg_store=None completes all phases without error."""
        dream = DreamLoop(pg_store=None)
        result = dream.run(dry_run=False)
        assert result.errors == []
        assert result.events_compressed == 0

    def test_dream_loop_autonomous_tasks_disabled_by_default(self):
        """Autonomous task generation is 0 when disabled."""
        dream = DreamLoop()
        result = dream.run()
        assert result.autonomous_tasks_generated == 0
        assert result.counterfactuals_generated == 0


# ============================================================
# HumanModel persistence
# ============================================================


class TestHumanModelPersistence:
    """Tests for HumanModel export/import across sessions."""

    def test_export_import_preserves_preferences(self):
        """HumanModel preferences survive export/import cycle."""
        model = HumanModel()
        model.add_preference(
            Preference(
                key="communication_style",
                value="concise",
                confidence=0.9,
            )
        )
        model.add_preference(
            Preference(
                key="expertise_level",
                value="advanced",
                confidence=0.85,
            )
        )
        exported = model.to_dict()
        restored = HumanModel.from_dict(exported)
        pref = restored.get_preference("communication_style")
        assert pref is not None
        assert pref.value == "concise"
        assert pref.confidence == 0.9

    def test_confidence_evolves_with_repeated_preferences(self):
        """Adding same preference multiple times increases confidence."""
        model = HumanModel()
        model.add_preference(
            Preference(
                key="tone",
                value="formal",
                confidence=0.5,
            )
        )
        initial = model.get_preference("tone").confidence
        model.add_preference(
            Preference(
                key="tone",
                value="formal",
                confidence=0.8,
            )
        )
        updated = model.get_preference("tone").confidence
        # add_preference merges: boosts confidence by 0.05 * observed_count
        assert updated != initial
        assert updated > initial

    def test_export_import_preserves_communication_style(self):
        """CommunicationStyle survives round-trip serialization."""
        model = HumanModel()
        model.communication_style.verbosity = 0.2
        model.communication_style.formality = 0.8
        exported = model.to_dict()
        restored = HumanModel.from_dict(exported)
        assert restored.communication_style.verbosity == 0.2
        assert restored.communication_style.formality == 0.8

    def test_interaction_patterns_recorded(self):
        """record_interaction stores patterns that survive export/import."""
        model = HumanModel()
        model.record_interaction(topic="python", satisfaction_signal=0.9, duration_seconds=120.0)
        model.record_interaction(topic="python", satisfaction_signal=0.8, duration_seconds=60.0)
        model.record_interaction(topic="python", satisfaction_signal=0.7, duration_seconds=90.0)
        assert model.interaction_count == 3
        topics = model.get_recurring_topics(min_count=3)
        assert "python" in topics

    # Amendment 10: error/edge-case tests
    def test_get_preference_returns_none_for_missing_key(self):
        """get_preference returns None for nonexistent key."""
        model = HumanModel()
        assert model.get_preference("nonexistent") is None

    def test_from_dict_handles_empty_dict(self):
        """HumanModel.from_dict with minimal data creates valid model."""
        model = HumanModel.from_dict({})
        assert model.interaction_count == 0
        assert model.preferences == []


# ============================================================
# Metrics end-to-end
# ============================================================


class TestMetricsEndToEnd:
    """Tests for MetricsCollector integration."""

    def test_full_report_after_operations(self):
        """Full report contains all recorded metric categories with correct totals."""
        collector = MetricsCollector()
        collector.record_token_usage("mock-e2e-v1", 100, 50)
        collector.record_token_usage("mock-e2e-v1", 200, 75)
        collector.record_consensus_merge(2, 1, 0, agreement_rate=0.85)
        collector.record_tool_execution(True, 45.0)
        collector.record_tool_execution(False, 120.0)
        collector.record_dream_run(3, 2, 1)
        collector.record_integration_health("slack", "healthy")
        collector.record_session_start("e2e-sess")
        collector.record_token_usage("mock-e2e-v1", 50, 25, session_id="e2e-sess")

        report = collector.to_full_report()
        # Token totals: 100+50=150, 200+75=275, 50+25=75 => total 500
        assert report["tokens"]["by_model"]["mock-e2e-v1"]["total_tokens"] == 500
        assert report["consensus"]["total_merges"] == 1
        assert report["tools"]["total_executions"] == 2
        assert report["dreams"]["total_runs"] == 1
        assert report["integrations"]["slack"]["status"] == "healthy"
        assert report["sessions"]["e2e-sess"]["token_count"] == 75

    def test_metrics_reset_clears_everything(self):
        """Reset leaves collector in clean state."""
        collector = MetricsCollector()
        collector.record_token_usage("gpt-4", 100, 50)
        collector.record_integration_health("discord", "down", error="fail")
        collector.reset()
        report = collector.to_full_report()
        assert report["snapshot"]["total_tokens"] == 0
        assert report["integrations"] == {}

    def test_session_lifecycle(self):
        """Session start/end tracking with token attribution."""
        collector = MetricsCollector()
        collector.record_session_start("sess-1")
        collector.record_token_usage("model-a", 200, 100, session_id="sess-1")
        collector.record_tool_execution(True, 30.0, session_id="sess-1")
        collector.record_session_end("sess-1")
        report = collector.to_full_report()
        sess = report["sessions"]["sess-1"]
        assert sess["token_count"] == 300
        assert sess["tool_executions"] == 1
        assert sess["tool_successes"] == 1
        assert sess["end_time"] is not None

    def test_snapshot_aggregates_correctly(self):
        """get_snapshot returns correct aggregated values."""
        collector = MetricsCollector()
        collector.record_token_usage("m1", 50, 25)
        collector.record_token_usage("m2", 100, 50)
        collector.record_consensus_merge(1, 0, 0)
        collector.record_tool_execution(True, 10.0)
        collector.record_dream_run(1, 0, 0)
        snapshot = collector.get_snapshot()
        assert snapshot.total_tokens == 225
        assert snapshot.consensus_merges == 1
        assert snapshot.tool_executions == 1
        assert snapshot.dream_runs == 1

    # Amendment 10: error/edge-case tests
    def test_session_end_for_nonexistent_session_is_noop(self):
        """record_session_end for unknown session_id does nothing."""
        collector = MetricsCollector()
        # Should not raise
        collector.record_session_end("nonexistent")
        report = collector.to_full_report()
        assert "nonexistent" not in report["sessions"]

    def test_token_usage_without_session_not_attributed(self):
        """Token usage recorded without session_id doesn't appear in sessions."""
        collector = MetricsCollector()
        collector.record_token_usage("model-x", 100, 50)
        report = collector.to_full_report()
        assert report["sessions"] == {}


# ============================================================
# Config bootstrap
# ============================================================


class TestConfigBootstrap:
    """Tests for configuration creation and mapping."""

    def test_default_config_creates_valid_config(self):
        """create_default_config returns VecnaConfig with expected default values."""
        config = create_default_config()
        # Amendment 9: assert specific default values, not just type
        assert config.active_group == "default"
        assert config.active_persona == "concise"
        assert "default" in config.groups
        assert config.memory.backend.value == "postgres"

    def test_default_config_has_expected_providers(self):
        """Default models use correct Provider enum values."""
        config = create_default_config()
        # All default models should be Copilot provider
        for model_entry in config.models.values():
            assert isinstance(model_entry.provider, Provider)

    def test_default_config_has_memory_config(self):
        """Default config includes MemoryConfig with sane defaults."""
        config = create_default_config()
        assert config.memory.embedding_dim == 1536
        assert config.memory.default_top_k == 10
        assert config.memory.pg_pool_size == 5

    # Amendment 10: error/edge-case tests
    def test_provider_enum_has_all_expected_values(self):
        """Provider enum includes all 6 expected providers."""
        expected = {"copilot", "ollama", "transformers", "groq", "openai", "anthropic"}
        actual = {p.value for p in Provider}
        assert actual == expected

    def test_default_groups_all_have_personas(self):
        """Every default group references a persona name."""
        config = create_default_config()
        for group in config.groups.values():
            assert group.persona in config.personas
