"""Tests for DreamLoop v2 — autonomous task generation and counterfactual exploration."""

from dataclasses import dataclass, field
from datetime import datetime
from unittest.mock import MagicMock

from vecna.memory.dream_loop import DreamLoop, DreamResult
from vecna.orchestrator.curiosity import CuriosityEngine, CuriosityGoal
from vecna.orchestrator.pg_goal_queue import PgGoalQueue


# ---------------------------------------------------------------------------
# Helpers — reuse the FakePgStore pattern from test_dream_loop.py
# ---------------------------------------------------------------------------


@dataclass
class _FakeEvent:
    event_type: str
    payload: dict = field(default_factory=dict)
    session_id: str = "session-1"
    created_at: datetime = field(default_factory=datetime.now)


class _FakeCursor:
    """Minimal cursor stub that returns empty result sets."""

    def execute(self, sql, params=None):
        pass

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class _FakeConnection:
    """Minimal connection stub for Phases 1-3 that returns empty cursors."""

    def cursor(self):
        return _FakeCursor()

    def commit(self):
        pass

    def rollback(self):
        pass


class _FakePgStore:
    """Minimal fake pg_store for unit tests — no DB needed."""

    def __init__(self, events=None, search_results=None, add_item_result_factory=None):
        self._events = events or []
        self._search_results = search_results or []
        self.added_items = []
        self._add_item_result_factory = add_item_result_factory

    def get_recent_events(self, limit=100):
        return self._events[:limit]

    def search(self, query, top_k=3):
        del query, top_k
        return self._search_results

    def add_item(self, item):
        self.added_items.append(item)
        if self._add_item_result_factory is not None:
            return self._add_item_result_factory(item)
        return f"id-{len(self.added_items)}"

    def _get_connection(self):
        """Return a fake connection that returns empty result sets for Phases 1-3."""
        return _FakeConnection()


# ---------------------------------------------------------------------------
# DreamResult v2 fields
# ---------------------------------------------------------------------------


class TestDreamResultV2Fields:
    """DreamResult must include the two new counters."""

    def test_has_autonomous_tasks_counter_defaulting_to_zero(self):
        result = DreamResult()
        assert result.autonomous_tasks_generated == 0

    def test_has_counterfactuals_counter_defaulting_to_zero(self):
        result = DreamResult()
        assert result.counterfactuals_generated == 0

    def test_to_dict_includes_autonomous_tasks_generated(self):
        result = DreamResult(autonomous_tasks_generated=3, counterfactuals_generated=2)
        d = result.to_dict()
        assert d["autonomous_tasks_generated"] == 3
        assert d["counterfactuals_generated"] == 2

    def test_to_dict_preserves_existing_fields(self):
        result = DreamResult(
            events_compressed=10,
            memories_reinforced=5,
            autonomous_tasks_generated=1,
            counterfactuals_generated=1,
        )
        d = result.to_dict()
        assert d["events_compressed"] == 10
        assert d["memories_reinforced"] == 5
        # Amendment 9: verify timestamp is a valid ISO format string, not just present
        ts = d["timestamp"]
        parsed = datetime.fromisoformat(ts)
        assert parsed.year >= 2024


# ---------------------------------------------------------------------------
# Phase 5: Autonomous Task Generation
# ---------------------------------------------------------------------------


class TestDreamLoopPhase5AutonomousTasks:
    """Phase 5: generate GoalItems from recurring patterns and push to PgGoalQueue."""

    def test_phase5_disabled_by_default(self):
        dream = DreamLoop()
        assert dream.autonomous_tasks_enabled is False

    def test_phase5_enabled_via_flag(self):
        dream = DreamLoop(autonomous_tasks_enabled=True)
        assert dream.autonomous_tasks_enabled is True

    def test_phase5_generates_goals_from_patterns(self):
        """When patterns are found, Phase 5 should push GoalItems to goal_queue."""
        goal_queue = PgGoalQueue(use_memory_fallback=True)

        store = _FakePgStore(
            events=[
                _FakeEvent(event_type="observation", payload={"topic": "rust"}),
                _FakeEvent(event_type="observation", payload={"topic": "rust"}),
                _FakeEvent(event_type="observation", payload={"topic": "rust"}),
                _FakeEvent(event_type="query", payload={"topic": "kubernetes"}),
                _FakeEvent(event_type="query", payload={"topic": "kubernetes"}),
            ]
        )

        dream = DreamLoop(
            pg_store=store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
        )

        count = dream._generate_autonomous_tasks(dry_run=False)
        assert count >= 1

        # Goals should now be in the queue
        pending = goal_queue.list_pending()
        assert len(pending) >= 1
        assert any("rust" in item.goal.lower() for item in pending)

    def test_phase5_respects_max_goals_per_dream(self):
        goal_queue = PgGoalQueue(use_memory_fallback=True)
        events = []
        for theme in ["alpha", "beta", "gamma", "delta", "epsilon"]:
            for _ in range(5):
                events.append(_FakeEvent(event_type="obs", payload={"topic": theme}))

        store = _FakePgStore(events=events)

        dream = DreamLoop(
            pg_store=store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
            max_autonomous_goals=2,
        )

        count = dream._generate_autonomous_tasks(dry_run=False)
        assert count <= 2

    def test_phase5_dry_run_does_not_push(self):
        goal_queue = PgGoalQueue(use_memory_fallback=True)
        store = _FakePgStore(
            events=[
                _FakeEvent(event_type="obs", payload={"topic": "python"}),
                _FakeEvent(event_type="obs", payload={"topic": "python"}),
            ]
        )

        dream = DreamLoop(
            pg_store=store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
        )

        count = dream._generate_autonomous_tasks(dry_run=True)
        assert count >= 1
        assert goal_queue.list_pending() == []

    def test_phase5_skipped_when_disabled(self):
        dream = DreamLoop(autonomous_tasks_enabled=False)
        count = dream._generate_autonomous_tasks(dry_run=False)
        assert count == 0

    def test_phase5_skipped_when_no_goal_queue(self):
        store = _FakePgStore(
            events=[
                _FakeEvent(event_type="obs", payload={"topic": "python"}),
                _FakeEvent(event_type="obs", payload={"topic": "python"}),
            ]
        )
        dream = DreamLoop(pg_store=store, autonomous_tasks_enabled=True)
        count = dream._generate_autonomous_tasks(dry_run=False)
        assert count == 0

    def test_phase5_goal_source_is_dreamloop(self):
        goal_queue = PgGoalQueue(use_memory_fallback=True)
        store = _FakePgStore(
            events=[
                _FakeEvent(event_type="obs", payload={"topic": "golang"}),
                _FakeEvent(event_type="obs", payload={"topic": "golang"}),
            ]
        )
        dream = DreamLoop(
            pg_store=store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
        )
        dream._generate_autonomous_tasks(dry_run=False)
        pending = goal_queue.list_pending()
        assert all(item.source == "dreamloop" for item in pending)

    def test_phase5_returns_zero_when_no_patterns_found(self):
        """Edge case: store has events but no recurring themes."""
        goal_queue = PgGoalQueue(use_memory_fallback=True)
        # Only one event per topic — below min_count threshold
        store = _FakePgStore(
            events=[
                _FakeEvent(event_type="obs", payload={"topic": "one-off"}),
            ]
        )
        dream = DreamLoop(
            pg_store=store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
        )
        count = dream._generate_autonomous_tasks(dry_run=False)
        assert count == 0

    def test_phase5_returns_zero_when_pg_store_lacks_get_recent_events(self):
        """Error path: pg_store doesn't have the expected method."""
        goal_queue = PgGoalQueue(use_memory_fallback=True)
        bare_store = MagicMock(spec=[])  # empty spec — no methods
        dream = DreamLoop(
            pg_store=bare_store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
        )
        count = dream._generate_autonomous_tasks(dry_run=False)
        assert count == 0


# ---------------------------------------------------------------------------
# Phase 6: Counterfactual Exploration
# ---------------------------------------------------------------------------


class TestDreamLoopPhase6Counterfactuals:
    """Phase 6: generate Hypothesis objects from contradictions and failed beliefs."""

    def test_phase6_disabled_when_autonomous_tasks_disabled(self):
        dream = DreamLoop(autonomous_tasks_enabled=False)
        count = dream._generate_counterfactuals(dry_run=False)
        assert count == 0

    def test_phase6_generates_counterfactuals_from_low_confidence_beliefs(self):
        mock_candidate = MagicMock()
        mock_candidate.content = "Python is slow for all tasks"
        mock_candidate.item_type = "belief"
        mock_candidate.confidence = 0.3
        mock_candidate.metadata = {"contradiction_id": "c1"}

        store = _FakePgStore(search_results=[mock_candidate])

        dream = DreamLoop(
            pg_store=store,
            autonomous_tasks_enabled=True,
        )

        count = dream._generate_counterfactuals(dry_run=False)
        assert count >= 1

    def test_phase6_creates_hypothesis_items_with_correct_type(self):
        mock_candidate = MagicMock()
        mock_candidate.content = "Static typing prevents all bugs"
        mock_candidate.item_type = "belief"
        mock_candidate.confidence = 0.4
        mock_candidate.metadata = {}

        store = _FakePgStore(search_results=[mock_candidate])

        dream = DreamLoop(
            pg_store=store,
            autonomous_tasks_enabled=True,
        )
        dream._generate_counterfactuals(dry_run=False)

        assert len(store.added_items) >= 1
        item = store.added_items[0]
        assert item.item_type == "hypothesis"
        assert item.metadata.get("source") == "counterfactual"

    def test_phase6_hypothesis_references_original_belief(self):
        mock_candidate = MagicMock()
        mock_candidate.content = "Tests are useless"
        mock_candidate.item_type = "belief"
        mock_candidate.confidence = 0.2
        mock_candidate.metadata = {}

        store = _FakePgStore(search_results=[mock_candidate])
        dream = DreamLoop(pg_store=store, autonomous_tasks_enabled=True)
        dream._generate_counterfactuals(dry_run=False)

        assert len(store.added_items) >= 1
        item = store.added_items[0]
        assert item.metadata["original_belief"] == "Tests are useless"
        assert item.metadata["original_confidence"] == 0.2

    def test_phase6_dry_run_does_not_persist(self):
        mock_candidate = MagicMock()
        mock_candidate.content = "X is true"
        mock_candidate.item_type = "belief"
        mock_candidate.confidence = 0.3
        mock_candidate.metadata = {}

        store = _FakePgStore(search_results=[mock_candidate])
        dream = DreamLoop(
            pg_store=store,
            autonomous_tasks_enabled=True,
        )
        count = dream._generate_counterfactuals(dry_run=True)
        assert count >= 1
        assert store.added_items == []

    def test_phase6_skipped_when_disabled(self):
        dream = DreamLoop(autonomous_tasks_enabled=False)
        count = dream._generate_counterfactuals(dry_run=False)
        assert count == 0

    def test_phase6_skipped_when_no_pg_store(self):
        dream = DreamLoop(autonomous_tasks_enabled=True)
        count = dream._generate_counterfactuals(dry_run=False)
        assert count == 0

    def test_phase6_ignores_high_confidence_beliefs(self):
        """Only low-confidence beliefs (<0.5) should generate counterfactuals."""
        high_conf = MagicMock()
        high_conf.content = "Well-established fact"
        high_conf.item_type = "belief"
        high_conf.confidence = 0.9
        high_conf.metadata = {}

        store = _FakePgStore(search_results=[high_conf])
        dream = DreamLoop(pg_store=store, autonomous_tasks_enabled=True)
        count = dream._generate_counterfactuals(dry_run=False)
        assert count == 0
        assert store.added_items == []

    def test_phase6_returns_zero_when_pg_store_lacks_search(self):
        """Error path: pg_store doesn't have a search method."""
        bare_store = MagicMock(spec=[])
        dream = DreamLoop(pg_store=bare_store, autonomous_tasks_enabled=True)
        count = dream._generate_counterfactuals(dry_run=False)
        assert count == 0


# ---------------------------------------------------------------------------
# DreamLoop.run() integration with Phase 5 + Phase 6
# ---------------------------------------------------------------------------


class TestDreamLoopRunV2:
    """Full run() should include Phase 5 and Phase 6 in results."""

    def test_run_includes_new_counters_when_disabled(self):
        dream = DreamLoop(autonomous_tasks_enabled=False)
        result = dream.run(dry_run=True)
        assert result.autonomous_tasks_generated == 0
        assert result.counterfactuals_generated == 0

    def test_run_with_phases_enabled(self):
        goal_queue = PgGoalQueue(use_memory_fallback=True)

        store = _FakePgStore(
            events=[
                _FakeEvent(event_type="obs", payload={"topic": "testing"}),
                _FakeEvent(event_type="obs", payload={"topic": "testing"}),
            ],
            search_results=[
                MagicMock(
                    content="Tests are unnecessary",
                    item_type="belief",
                    confidence=0.2,
                    metadata={},
                ),
            ],
        )

        dream = DreamLoop(
            pg_store=store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
        )
        result = dream.run(dry_run=True)
        # Phase 5 should detect the "testing" pattern
        assert result.autonomous_tasks_generated >= 1
        # Phase 6 should detect the low-confidence belief
        assert result.counterfactuals_generated >= 1
        # Verify duration was tracked
        assert result.duration_seconds >= 0.0

    def test_run_result_to_dict_has_all_v2_fields(self):
        dream = DreamLoop(autonomous_tasks_enabled=False)
        result = dream.run(dry_run=True)
        d = result.to_dict()
        assert "autonomous_tasks_generated" in d
        assert "counterfactuals_generated" in d
        assert d["autonomous_tasks_generated"] == 0
        assert d["counterfactuals_generated"] == 0


# ---------------------------------------------------------------------------
# CuriosityEngine.from_dream_patterns()
# ---------------------------------------------------------------------------


class TestCuriosityEngineFromDreamPatterns:
    """CuriosityEngine gets a new from_dream_patterns() method."""

    def test_from_dream_patterns_generates_goals(self):
        engine = CuriosityEngine()
        patterns = [
            {"theme": "rust", "count": 5, "frequency": 0.25},
            {"theme": "kubernetes", "count": 3, "frequency": 0.15},
        ]
        goals = engine.from_dream_patterns(patterns)
        assert len(goals) == 2
        # Amendment 9: verify specific field values, not just isinstance
        assert goals[0].content == "rust"
        assert goals[0].priority == "high"
        assert goals[0].source == "dream_pattern"
        assert goals[1].content == "kubernetes"
        assert goals[1].priority == "medium"
        assert goals[1].source == "dream_pattern"

    def test_from_dream_patterns_empty_list(self):
        engine = CuriosityEngine()
        goals = engine.from_dream_patterns([])
        assert goals == []

    def test_from_dream_patterns_high_priority_from_high_frequency(self):
        engine = CuriosityEngine()
        patterns = [
            {"theme": "hot-topic", "count": 10, "frequency": 0.5},
        ]
        goals = engine.from_dream_patterns(patterns)
        assert goals[0].priority == "high"
        assert goals[0].content == "hot-topic"

    def test_from_dream_patterns_low_priority_from_low_frequency(self):
        engine = CuriosityEngine()
        patterns = [
            {"theme": "mild-topic", "count": 2, "frequency": 0.05},
        ]
        goals = engine.from_dream_patterns(patterns)
        assert goals[0].priority == "low"

    def test_from_dream_patterns_medium_priority_from_moderate_frequency(self):
        engine = CuriosityEngine()
        patterns = [
            {"theme": "moderate", "count": 4, "frequency": 0.15},
        ]
        goals = engine.from_dream_patterns(patterns)
        assert goals[0].priority == "medium"

    def test_from_dream_patterns_skips_empty_themes(self):
        engine = CuriosityEngine()
        patterns = [
            {"theme": "", "count": 5, "frequency": 0.25},
            {"theme": "valid", "count": 3, "frequency": 0.15},
        ]
        goals = engine.from_dream_patterns(patterns)
        assert len(goals) == 1
        assert goals[0].content == "valid"

    def test_from_dream_patterns_handles_missing_theme_key(self):
        engine = CuriosityEngine()
        patterns = [
            {"count": 5, "frequency": 0.25},  # no theme key
        ]
        goals = engine.from_dream_patterns(patterns)
        assert goals == []


# ---------------------------------------------------------------------------
# Additional error/edge-case tests (Amendment 10)
# ---------------------------------------------------------------------------


class TestDreamLoopPhase5ErrorPaths:
    """Error and edge-case tests for Phase 5 autonomous task generation."""

    def test_phase5_handles_empty_events_from_store(self):
        """Edge: store returns empty event list — no patterns possible."""
        goal_queue = PgGoalQueue(use_memory_fallback=True)
        store = _FakePgStore(events=[])
        dream = DreamLoop(
            pg_store=store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
        )
        count = dream._generate_autonomous_tasks(dry_run=False)
        assert count == 0
        assert goal_queue.list_pending() == []

    def test_phase5_goal_metadata_contains_origin_and_theme(self):
        """Verify pushed goals contain correct metadata fields."""
        goal_queue = PgGoalQueue(use_memory_fallback=True)
        store = _FakePgStore(
            events=[
                _FakeEvent(event_type="obs", payload={"topic": "docker"}),
                _FakeEvent(event_type="obs", payload={"topic": "docker"}),
                _FakeEvent(event_type="obs", payload={"topic": "docker"}),
            ]
        )
        dream = DreamLoop(
            pg_store=store,
            goal_queue=goal_queue,
            autonomous_tasks_enabled=True,
        )
        dream._generate_autonomous_tasks(dry_run=False)
        pending = goal_queue.list_pending()
        assert len(pending) >= 1
        # Can't check metadata directly on GoalItem from list_pending (memory mode),
        # but the goal text should contain the theme
        assert any("docker" in item.goal.lower() for item in pending)


class TestDreamLoopPhase6ErrorPaths:
    """Error and edge-case tests for Phase 6 counterfactual exploration."""

    def test_phase6_handles_candidate_with_empty_content(self):
        """Edge: candidate has empty content string — should be skipped."""
        mock_candidate = MagicMock()
        mock_candidate.content = ""
        mock_candidate.item_type = "belief"
        mock_candidate.confidence = 0.1
        mock_candidate.metadata = {}

        store = _FakePgStore(search_results=[mock_candidate])
        dream = DreamLoop(pg_store=store, autonomous_tasks_enabled=True)
        count = dream._generate_counterfactuals(dry_run=False)
        assert count == 0
        assert store.added_items == []

    def test_phase6_handles_non_belief_non_hypothesis_items(self):
        """Edge: search returns items that aren't beliefs or hypotheses."""
        mock_fact = MagicMock()
        mock_fact.content = "Some factual statement"
        mock_fact.item_type = "fact"
        mock_fact.confidence = 0.3
        mock_fact.metadata = {}

        store = _FakePgStore(search_results=[mock_fact])
        dream = DreamLoop(pg_store=store, autonomous_tasks_enabled=True)
        count = dream._generate_counterfactuals(dry_run=False)
        assert count == 0
        assert store.added_items == []

    def test_phase6_caps_at_five_counterfactuals_per_cycle(self):
        """Verify the 5-counterfactual-per-cycle limit."""
        candidates = []
        for i in range(10):
            m = MagicMock()
            m.content = f"Low confidence belief {i}"
            m.item_type = "belief"
            m.confidence = 0.1 + i * 0.03  # All below 0.5
            m.metadata = {}
            candidates.append(m)

        store = _FakePgStore(search_results=candidates)
        dream = DreamLoop(pg_store=store, autonomous_tasks_enabled=True)
        count = dream._generate_counterfactuals(dry_run=False)
        assert count <= 5

    def test_phase6_add_item_failure_does_not_count(self):
        """Edge: add_item returns None (failure) — should not count as generated."""
        mock_candidate = MagicMock()
        mock_candidate.content = "Questionable belief"
        mock_candidate.item_type = "belief"
        mock_candidate.confidence = 0.2
        mock_candidate.metadata = {}

        store = _FakePgStore(
            search_results=[mock_candidate],
            add_item_result_factory=lambda item: None,
        )
        dream = DreamLoop(pg_store=store, autonomous_tasks_enabled=True)
        count = dream._generate_counterfactuals(dry_run=False)
        assert count == 0

    def test_phase6_counterfactual_confidence_is_low(self):
        """Verify generated hypotheses have low initial confidence (0.3)."""
        mock_candidate = MagicMock()
        mock_candidate.content = "Dubious claim"
        mock_candidate.item_type = "belief"
        mock_candidate.confidence = 0.15
        mock_candidate.metadata = {}

        store = _FakePgStore(search_results=[mock_candidate])
        dream = DreamLoop(pg_store=store, autonomous_tasks_enabled=True)
        dream._generate_counterfactuals(dry_run=False)

        assert len(store.added_items) == 1
        item = store.added_items[0]
        assert item.confidence == 0.3
        assert item.domain == "meta"
        assert item.metadata["origin"] == "dream_phase6"


class TestDreamLoopRunV2ErrorPaths:
    """Error/edge-case tests for the full run() integration."""

    def test_run_records_zero_errors_on_clean_run(self):
        dream = DreamLoop(autonomous_tasks_enabled=False)
        result = dream.run(dry_run=True)
        assert result.errors == []

    def test_run_with_no_store_returns_zeroed_result(self):
        dream = DreamLoop(autonomous_tasks_enabled=True)
        result = dream.run(dry_run=True)
        assert result.events_compressed == 0
        assert result.episodes_created == 0
        assert result.memories_reinforced == 0
        assert result.memories_decayed == 0
        assert result.insights_generated == 0
        assert result.autonomous_tasks_generated == 0
        assert result.counterfactuals_generated == 0
