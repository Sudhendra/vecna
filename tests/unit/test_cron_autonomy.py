"""Tests for cron-based autonomous operation — HeartbeatAction and HeartbeatConfig."""

import time
from datetime import datetime, timedelta

from vecna.orchestrator.heartbeat import HeartbeatAction, HeartbeatConfig, HeartbeatRunner


class TestHeartbeatActions:
    """Tests for HeartbeatAction scheduling logic."""

    def test_check_goals_action_should_run_when_elapsed_exceeds_interval(self):
        action = HeartbeatAction(
            name="check_goals",
            description="Check for pending autonomous goals",
            interval_seconds=900,
        )
        assert action.should_run(elapsed_seconds=1000) is True

    def test_check_goals_action_should_not_run_when_elapsed_below_interval(self):
        action = HeartbeatAction(
            name="check_goals",
            description="Check for pending autonomous goals",
            interval_seconds=900,
        )
        assert action.should_run(elapsed_seconds=100) is False

    def test_dream_action_daily_interval_not_ready(self):
        action = HeartbeatAction(
            name="dream",
            description="Run dream loop consolidation",
            interval_seconds=86400,
        )
        assert action.should_run(elapsed_seconds=3600) is False

    def test_dream_action_daily_interval_ready(self):
        action = HeartbeatAction(
            name="dream",
            description="Run dream loop consolidation",
            interval_seconds=86400,
        )
        assert action.should_run(elapsed_seconds=90000) is True

    def test_action_records_last_run_with_timestamp(self):
        action = HeartbeatAction(name="test", interval_seconds=60)
        assert action.last_run is None
        before = datetime.utcnow()
        action.mark_run()
        after = datetime.utcnow()
        assert action.last_run is not None
        assert before <= action.last_run <= after

    def test_should_run_at_exact_boundary(self):
        """Elapsed exactly equals interval should trigger."""
        action = HeartbeatAction(name="boundary", interval_seconds=300)
        assert action.should_run(elapsed_seconds=300) is True

    def test_should_not_run_at_zero_elapsed(self):
        action = HeartbeatAction(name="zero", interval_seconds=60)
        assert action.should_run(elapsed_seconds=0) is False

    def test_action_has_description_field(self):
        action = HeartbeatAction(
            name="test_desc",
            description="A descriptive action",
            interval_seconds=120,
        )
        assert action.description == "A descriptive action"

    def test_action_default_description_is_empty(self):
        action = HeartbeatAction(name="minimal", interval_seconds=60)
        assert action.description == ""

    def test_action_serializes_to_dict(self):
        """HeartbeatAction should support to_dict (SerializableMixin)."""
        action = HeartbeatAction(
            name="serialize_test",
            description="Testing serialization",
            interval_seconds=600,
        )
        d = action.to_dict()
        assert d["name"] == "serialize_test"
        assert d["description"] == "Testing serialization"
        assert d["interval_seconds"] == 600
        assert d["last_run"] is None

    def test_action_serializes_last_run_as_iso(self):
        action = HeartbeatAction(name="ts", interval_seconds=60)
        action.mark_run()
        d = action.to_dict()
        # last_run should be an ISO string, not a datetime object
        assert isinstance(d["last_run"], str)
        # Should be parseable back to datetime
        parsed = datetime.fromisoformat(d["last_run"])
        assert isinstance(parsed, datetime)


class TestHeartbeatActionEdgeCases:
    """Error and edge-case tests (Amendment 10)."""

    def test_negative_elapsed_seconds_does_not_run(self):
        action = HeartbeatAction(name="neg", interval_seconds=60)
        assert action.should_run(elapsed_seconds=-10) is False

    def test_negative_interval_always_runs(self):
        """An action with interval_seconds <= 0 should always run (run as often as possible)."""
        action = HeartbeatAction(name="eager", interval_seconds=0)
        assert action.should_run(elapsed_seconds=0) is True
        action2 = HeartbeatAction(name="negative_interval", interval_seconds=-1)
        assert action2.should_run(elapsed_seconds=0) is True

    def test_very_large_elapsed_runs(self):
        action = HeartbeatAction(name="stale", interval_seconds=60)
        assert action.should_run(elapsed_seconds=999_999_999) is True

    def test_mark_run_updates_timestamp_each_call(self):
        action = HeartbeatAction(name="multi", interval_seconds=60)
        action.mark_run()
        first_run = action.last_run
        # Small sleep to ensure timestamp differs
        time.sleep(0.01)
        action.mark_run()
        second_run = action.last_run
        assert second_run is not None
        assert first_run is not None
        assert second_run >= first_run

    def test_float_elapsed_seconds(self):
        """should_run should handle float elapsed values."""
        action = HeartbeatAction(name="float_test", interval_seconds=10)
        assert action.should_run(elapsed_seconds=10.5) is True
        assert action.should_run(elapsed_seconds=9.9) is False


class TestHeartbeatConfig:
    """Tests for HeartbeatConfig default action system."""

    def test_default_actions_include_required_names(self):
        config = HeartbeatConfig()
        assert len(config.actions) > 0
        action_names = [a.name for a in config.actions]
        assert "check_goals" in action_names
        assert "dream" in action_names
        assert "curiosity" in action_names

    def test_default_check_goals_interval(self):
        config = HeartbeatConfig()
        check_goals = next(a for a in config.actions if a.name == "check_goals")
        assert check_goals.interval_seconds == 900

    def test_default_dream_interval(self):
        config = HeartbeatConfig()
        dream = next(a for a in config.actions if a.name == "dream")
        assert dream.interval_seconds == 86400

    def test_default_curiosity_interval(self):
        config = HeartbeatConfig()
        curiosity = next(a for a in config.actions if a.name == "curiosity")
        # Curiosity should have an interval between check_goals and dream
        assert 0 < curiosity.interval_seconds < 86400

    def test_config_preserves_existing_fields(self):
        """HeartbeatConfig should still have interval_seconds, jitter_seconds, max_goals_per_tick."""
        config = HeartbeatConfig()
        assert config.interval_seconds == 900
        assert config.jitter_seconds == 90
        assert config.max_goals_per_tick == 3

    def test_custom_actions_override_defaults(self):
        custom_action = HeartbeatAction(name="custom", interval_seconds=42)
        config = HeartbeatConfig(actions=[custom_action])
        assert len(config.actions) == 1
        assert config.actions[0].name == "custom"
        assert config.actions[0].interval_seconds == 42


class TestHeartbeatConfigEdgeCases:
    """Edge cases for HeartbeatConfig (Amendment 10)."""

    def test_empty_actions_list(self):
        config = HeartbeatConfig(actions=[])
        assert config.actions == []

    def test_actions_are_independent_instances(self):
        """Each HeartbeatConfig should have its own action instances, not shared mutable state."""
        config1 = HeartbeatConfig()
        config2 = HeartbeatConfig()
        config1.actions[0].mark_run()
        # config2 actions should be unaffected
        assert config2.actions[0].last_run is None


class TestHeartbeatRunnerDueActions:
    """Tests for HeartbeatRunner.get_due_actions() scheduling integration."""

    def test_get_due_actions_returns_all_when_never_run(self):
        """Actions that have never run should all be due."""
        config = HeartbeatConfig()
        runner = HeartbeatRunner.__new__(HeartbeatRunner)
        runner.config = config
        runner.autonomy_loop = None
        runner.goal_queue = None
        due = runner.get_due_actions()
        assert len(due) == len(config.actions)
        due_names = [a.name for a in due]
        assert "check_goals" in due_names
        assert "dream" in due_names
        assert "curiosity" in due_names

    def test_get_due_actions_excludes_recently_run(self):
        """An action that just ran should not be due again immediately."""
        action = HeartbeatAction(name="recent", interval_seconds=3600)
        action.mark_run()
        config = HeartbeatConfig(actions=[action])
        runner = HeartbeatRunner.__new__(HeartbeatRunner)
        runner.config = config
        runner.autonomy_loop = None
        runner.goal_queue = None
        due = runner.get_due_actions()
        assert len(due) == 0

    def test_get_due_actions_includes_overdue(self):
        """An action whose last_run is older than its interval should be due."""
        action = HeartbeatAction(name="overdue", interval_seconds=60)
        action.last_run = datetime.utcnow() - timedelta(seconds=120)
        config = HeartbeatConfig(actions=[action])
        runner = HeartbeatRunner.__new__(HeartbeatRunner)
        runner.config = config
        runner.autonomy_loop = None
        runner.goal_queue = None
        due = runner.get_due_actions()
        assert len(due) == 1
        assert due[0].name == "overdue"
