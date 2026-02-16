"""E2E tests for heartbeat CLI commands."""

import json
import importlib

from click.testing import CliRunner

from vecna.cli.main import cli


def test_cli_heartbeat_tick_command_exists():
    runner = CliRunner()

    result = runner.invoke(cli, ["heartbeat", "--help"])

    assert result.exit_code == 0
    assert "tick" in result.output.lower()


def test_cli_heartbeat_tick_prints_status_when_queue_empty(tmp_path):
    runner = CliRunner()

    result = runner.invoke(
        cli,
        ["--skip-boot", "heartbeat", "tick"],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert "status" in result.output.lower()


def test_cli_heartbeat_tick_uses_configured_adapters(monkeypatch, tmp_path):
    runner = CliRunner()
    queue_path = tmp_path / "autonomy_queue.jsonl"
    queue_path.write_text(json.dumps({"goal_id": "g1", "goal": "process this"}) + "\n")

    sentinel_config = object()
    sentinel_adapters = [object(), object()]
    observed = {}

    class _FakeHiveLoop:
        config = sentinel_config
        adapters = sentinel_adapters

    class _FakeHive:
        loop = _FakeHiveLoop()

    class _FakeAutonomyLoop:
        def __init__(self, config=None, adapters=None, name="explorer", **_kwargs):
            observed["config"] = config
            observed["adapters"] = adapters
            observed["name"] = name

        def _extract_goal(self, item):
            return item.get("goal", "")

        async def _run_goal(self, goal, max_cycles=None):
            return f"done:{goal}"

        def _mark_completed(self, goal_queue, goal_id):
            observed["completed_goal_id"] = goal_id

        def _mark_failed(self, goal_queue, goal_id, error):
            observed["failed_goal_id"] = goal_id

    cli_main_module = importlib.import_module("vecna.cli.main")
    monkeypatch.setattr(cli_main_module, "get_hive", lambda use_config=True: _FakeHive())
    monkeypatch.setattr("vecna.orchestrator.autonomy.AutonomyLoop", _FakeAutonomyLoop)

    result = runner.invoke(
        cli,
        ["--skip-boot", "heartbeat", "tick", "--queue-path", str(queue_path), "--max-goals", "1"],
        env={"HOME": str(tmp_path)},
    )

    assert result.exit_code == 0
    assert observed["config"] is sentinel_config
    assert observed["adapters"] is sentinel_adapters
    assert observed["name"] == "explorer"
    assert observed["completed_goal_id"] == "g1"
