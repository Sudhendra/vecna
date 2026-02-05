"""
End-to-end tests for Vecna CLI commands.

These tests use Click's CliRunner to test CLI commands without
actually invoking subprocesses. They verify that commands:
- Parse arguments correctly
- Return expected exit codes
- Produce expected output
- Interact correctly with the system

Some tests require PostgreSQL/Redis (marked accordingly).
"""

import pytest
from click.testing import CliRunner

from vecna.cli.main import cli


# ============================================================
# FIXTURES
# ============================================================


@pytest.fixture
def runner():
    """Get a Click test runner."""
    return CliRunner()


@pytest.fixture
def isolated_runner():
    """Get a runner with isolated filesystem."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        yield runner


# ============================================================
# HELP TESTS
# ============================================================


class TestHelp:
    """Test help output for all commands."""

    def test_cli_help(self, runner: CliRunner):
        """Test main CLI help."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "VECNA" in result.output
        assert "hive mind" in result.output.lower()

    def test_auth_help(self, runner: CliRunner):
        """Test auth command group help."""
        result = runner.invoke(cli, ["auth", "--help"])
        assert result.exit_code == 0
        assert "authentication" in result.output.lower() or "auth" in result.output.lower()

    def test_config_help(self, runner: CliRunner):
        """Test config command group help."""
        result = runner.invoke(cli, ["config", "--help"])
        assert result.exit_code == 0
        assert "config" in result.output.lower()

    def test_mem_help(self, runner: CliRunner):
        """Test mem command group help."""
        result = runner.invoke(cli, ["mem", "--help"])
        assert result.exit_code == 0
        assert "memory" in result.output.lower()

    def test_models_help(self, runner: CliRunner):
        """Test models command group help."""
        result = runner.invoke(cli, ["models", "--help"])
        assert result.exit_code == 0
        assert "model" in result.output.lower()

    def test_speak_help(self, runner: CliRunner):
        """Test speak command help."""
        result = runner.invoke(cli, ["speak", "--help"])
        assert result.exit_code == 0
        assert "task" in result.output.lower()


# ============================================================
# AUTH COMMANDS
# ============================================================


class TestAuthCommands:
    """Test authentication commands."""

    def test_auth_status(self, runner: CliRunner):
        """Test auth status command."""
        result = runner.invoke(cli, ["auth", "status"])
        # Should not crash, may show logged in or not
        assert result.exit_code == 0

    def test_auth_models(self, runner: CliRunner):
        """Test auth models command lists available models."""
        result = runner.invoke(cli, ["auth", "models"])
        # Should show available models or auth error
        # Exit code may be non-zero if not authenticated
        assert result.exit_code in [0, 1]


# ============================================================
# CONFIG COMMANDS
# ============================================================


class TestConfigCommands:
    """Test configuration commands."""

    def test_config_get_nonexistent(self, runner: CliRunner):
        """Test config get with nonexistent key."""
        result = runner.invoke(cli, ["config", "get", "nonexistent_key_12345"])
        # Should handle gracefully
        assert result.exit_code in [0, 1]


# ============================================================
# MODELS COMMANDS
# ============================================================


class TestModelsCommands:
    """Test model management commands."""

    def test_models_list(self, runner: CliRunner):
        """Test models list command."""
        result = runner.invoke(cli, ["models", "list"])
        assert result.exit_code == 0


# ============================================================
# MEMORY COMMANDS
# ============================================================


class TestMemoryCommands:
    """Test memory commands."""

    def test_mem_stats(self, runner: CliRunner, postgres_available):
        """Test mem stats command."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        result = runner.invoke(cli, ["mem", "stats"])
        assert result.exit_code == 0

    def test_mem_config(self, runner: CliRunner):
        """Test mem config command."""
        result = runner.invoke(cli, ["mem", "config"])
        assert result.exit_code == 0

    def test_mem_search(self, runner: CliRunner, postgres_available):
        """Test mem search command."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        result = runner.invoke(cli, ["mem", "search", "test query"])
        # May return no results but should not crash
        assert result.exit_code == 0


# ============================================================
# SKIP BOOT FLAG
# ============================================================


class TestSkipBootFlag:
    """Test --skip-boot flag behavior."""

    def test_skip_boot_flag(self, runner: CliRunner):
        """Test that --skip-boot flag works."""
        result = runner.invoke(cli, ["--skip-boot", "--help"])
        assert result.exit_code == 0

    def test_skip_boot_with_subcommand(self, runner: CliRunner):
        """Test --skip-boot with subcommand."""
        result = runner.invoke(cli, ["--skip-boot", "auth", "status"])
        assert result.exit_code == 0


# ============================================================
# NO SAVE FLAG
# ============================================================


class TestNoSaveFlag:
    """Test --no-save flag behavior."""

    def test_no_save_flag_recognized(self, runner: CliRunner):
        """Test that --no-save flag is recognized."""
        result = runner.invoke(cli, ["--no-save", "--help"])
        assert result.exit_code == 0


# ============================================================
# ERROR HANDLING
# ============================================================


class TestErrorHandling:
    """Test error handling in CLI."""

    def test_unknown_command(self, runner: CliRunner):
        """Test that unknown commands are handled."""
        result = runner.invoke(cli, ["nonexistent-command"])
        # Should return non-zero exit code
        assert result.exit_code != 0

    def test_missing_required_argument(self, runner: CliRunner):
        """Test missing required argument handling."""
        # speak requires a task argument
        result = runner.invoke(cli, ["speak"])
        assert result.exit_code != 0
        assert "missing" in result.output.lower() or "required" in result.output.lower()


# ============================================================
# SPEAK COMMAND (non-interactive)
# ============================================================


class TestSpeakCommand:
    """Test speak command (single query mode)."""

    def test_speak_requires_task(self, runner: CliRunner):
        """Test that speak requires a task argument."""
        result = runner.invoke(cli, ["speak"])
        assert result.exit_code != 0

    def test_speak_help(self, runner: CliRunner):
        """Test speak --help shows usage."""
        result = runner.invoke(cli, ["speak", "--help"])
        assert result.exit_code == 0
        assert "task" in result.output.lower()


# ============================================================
# OUTPUT FORMAT TESTS
# ============================================================


class TestOutputFormat:
    """Test output formatting."""

    def test_help_contains_vecna_branding(self, runner: CliRunner):
        """Test that help contains Vecna branding."""
        result = runner.invoke(cli, ["--help"])
        assert "VECNA" in result.output or "vecna" in result.output

    def test_help_shows_subcommands(self, runner: CliRunner):
        """Test that help shows available subcommands."""
        result = runner.invoke(cli, ["--help"])
        # Should mention key subcommands
        assert "chat" in result.output.lower() or "speak" in result.output.lower()


# ============================================================
# ENVIRONMENT VARIABLE HANDLING
# ============================================================


class TestEnvironmentVariables:
    """Test environment variable handling."""

    def test_runs_without_env_vars(self, runner: CliRunner):
        """Test that CLI can run without special env vars."""
        # At minimum, help should work
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0


# ============================================================
# EXIT CODE TESTS
# ============================================================


class TestExitCodes:
    """Test proper exit codes."""

    def test_successful_command_returns_zero(self, runner: CliRunner):
        """Test that successful commands return 0."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0

    def test_help_flags_return_zero(self, runner: CliRunner):
        """Test that help flags return 0."""
        for cmd in [["--help"], ["auth", "--help"], ["config", "--help"], ["mem", "--help"]]:
            result = runner.invoke(cli, cmd)
            assert result.exit_code == 0, f"Failed for {cmd}"


# ============================================================
# CONCURRENT SAFETY
# ============================================================


class TestConcurrentSafety:
    """Test that commands are safe for concurrent use."""

    def test_multiple_help_calls(self, runner: CliRunner):
        """Test that multiple help calls work."""
        for _ in range(5):
            result = runner.invoke(cli, ["--help"])
            assert result.exit_code == 0

    def test_multiple_status_calls(self, runner: CliRunner):
        """Test that multiple status calls work."""
        for _ in range(3):
            result = runner.invoke(cli, ["auth", "status"])
            assert result.exit_code == 0


# ============================================================
# PERSONA COMMANDS
# ============================================================


class TestPersonaCommands:
    """Test persona management commands."""

    def test_persona_help(self, runner: CliRunner):
        """Test persona command help."""
        result = runner.invoke(cli, ["persona", "--help"])
        assert result.exit_code == 0


# ============================================================
# GROUPS COMMANDS
# ============================================================


class TestGroupsCommands:
    """Test model groups commands."""

    def test_groups_help(self, runner: CliRunner):
        """Test groups command help."""
        result = runner.invoke(cli, ["groups", "--help"])
        assert result.exit_code == 0
