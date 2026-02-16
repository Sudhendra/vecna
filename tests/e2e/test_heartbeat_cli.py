"""E2E tests for heartbeat CLI commands."""

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
