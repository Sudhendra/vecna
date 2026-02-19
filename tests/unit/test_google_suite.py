"""Tests for the Google Suite integration via gogcli."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from vecna.integrations.google_suite import (
    GoogleSuiteIntegration,
    GoogleSuiteCommand,
    GogcliResult,
    COMMAND_ALLOWLIST,
)


class TestGoogleSuiteCommand:
    def test_calendar_list_command(self):
        cmd = GoogleSuiteCommand.CALENDAR_LIST
        assert cmd.value == "cal events list"
        assert cmd.cli_args() == ["cal", "events", "list"]

    def test_gmail_list_command(self):
        cmd = GoogleSuiteCommand.GMAIL_LIST
        assert cmd.value == "gmail messages list"
        assert cmd.cli_args() == ["gmail", "messages", "list"]

    def test_contacts_list_command(self):
        cmd = GoogleSuiteCommand.CONTACTS_LIST
        assert cmd.value == "contacts list"
        assert cmd.cli_args() == ["contacts", "list"]

    def test_tasks_list_command(self):
        cmd = GoogleSuiteCommand.TASKS_LIST
        assert cmd.value == "tasks list"
        assert cmd.cli_args() == ["tasks", "list"]


class TestCommandAllowlist:
    def test_allowlist_contains_safe_commands(self):
        assert GoogleSuiteCommand.CALENDAR_LIST in COMMAND_ALLOWLIST
        assert GoogleSuiteCommand.GMAIL_LIST in COMMAND_ALLOWLIST
        assert GoogleSuiteCommand.CONTACTS_LIST in COMMAND_ALLOWLIST
        assert GoogleSuiteCommand.TASKS_LIST in COMMAND_ALLOWLIST

    def test_allowlist_is_frozen_and_has_expected_size(self):
        """Amendment 9: Assert specific size, not just type."""
        assert isinstance(COMMAND_ALLOWLIST, frozenset)
        assert len(COMMAND_ALLOWLIST) == 4

    def test_allowlist_is_immutable(self):
        """Verify frozenset cannot be mutated."""
        with pytest.raises(AttributeError):
            COMMAND_ALLOWLIST.add(GoogleSuiteCommand.CALENDAR_LIST)  # type: ignore[attr-defined]


class TestGogcliResult:
    def test_success_result(self):
        result = GogcliResult(
            success=True,
            command="cal events list",
            data=[{"title": "Meeting", "start": "2026-02-16T10:00:00"}],
        )
        assert result.success is True
        assert result.command == "cal events list"
        assert len(result.data) == 1
        assert result.data[0]["title"] == "Meeting"

    def test_error_result(self):
        result = GogcliResult(
            success=False,
            command="cal events list",
            error="gogcli not found",
        )
        assert result.success is False
        assert "not found" in result.error

    def test_result_to_dict_via_serializable_mixin(self):
        """Amendment 7: to_dict() comes from SerializableMixin, not custom method."""
        result = GogcliResult(
            success=True,
            command="tasks list",
            data=[{"title": "Buy groceries"}],
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["command"] == "tasks list"
        assert len(d["data"]) == 1
        assert d["data"][0]["title"] == "Buy groceries"
        # Verify all fields are present
        assert "error" in d
        assert "raw_output" in d

    def test_result_defaults(self):
        """Verify default field values."""
        result = GogcliResult()
        assert result.success is False
        assert result.command == ""
        assert result.data == []
        assert result.error == ""
        assert result.raw_output == ""


class TestGoogleSuiteIntegration:
    def test_integration_name(self):
        integration = GoogleSuiteIntegration()
        assert integration.name == "google_suite"

    def test_integration_disabled_by_default(self):
        integration = GoogleSuiteIntegration()
        assert integration.enabled is False

    def test_integration_description(self):
        integration = GoogleSuiteIntegration()
        assert "google" in integration.description.lower()
        assert "gogcli" in integration.description.lower()

    def test_required_credentials_empty(self):
        """gogcli manages its own auth via keychain — no creds needed."""
        integration = GoogleSuiteIntegration()
        assert integration.required_credentials == []

    def test_custom_binary_path(self):
        integration = GoogleSuiteIntegration(binary_path="/usr/local/bin/gogcli")
        assert integration.binary_path == "/usr/local/bin/gogcli"

    async def test_health_check_no_binary(self):
        """Health check should fail gracefully when gogcli is not installed."""
        integration = GoogleSuiteIntegration()
        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._check_binary",
            return_value=False,
        ):
            status = await integration.check_health()
            assert status.healthy is False
            assert (
                "not found" in status.message.lower() or "not installed" in status.message.lower()
            )
            assert status.name == "google_suite"

    async def test_health_check_binary_present(self):
        integration = GoogleSuiteIntegration()
        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._check_binary",
            return_value=True,
        ):
            status = await integration.check_health()
            assert status.healthy is True
            assert status.name == "google_suite"

    def test_command_not_in_allowlist_rejected(self):
        integration = GoogleSuiteIntegration()
        assert integration.is_command_allowed("rm -rf /") is False

    def test_command_in_allowlist_accepted(self):
        integration = GoogleSuiteIntegration()
        assert integration.is_command_allowed("cal events list") is True

    def test_arbitrary_string_not_in_allowlist(self):
        integration = GoogleSuiteIntegration()
        assert integration.is_command_allowed("gmail send --to evil@example.com") is False

    async def test_start_and_stop(self):
        """Test that start/stop lifecycle works."""
        integration = GoogleSuiteIntegration()
        await integration.start()
        assert integration._running is True
        await integration.stop()
        assert integration._running is False


class TestGoogleSuiteExecution:
    async def test_run_command_parses_json_output(self):
        integration = GoogleSuiteIntegration()
        mock_output = json.dumps(
            [
                {"title": "Team standup", "start": "2026-02-16T09:00:00"},
                {"title": "1:1 with boss", "start": "2026-02-16T14:00:00"},
            ]
        )

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await integration.run_command(GoogleSuiteCommand.CALENDAR_LIST)
            assert result.success is True
            assert len(result.data) == 2
            assert result.data[0]["title"] == "Team standup"
            assert result.data[1]["title"] == "1:1 with boss"

    async def test_run_command_handles_error(self):
        integration = GoogleSuiteIntegration()

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(1, "", "authentication failed"),
        ):
            result = await integration.run_command(GoogleSuiteCommand.CALENDAR_LIST)
            assert result.success is False
            assert "authentication" in result.error.lower()

    async def test_run_command_handles_invalid_json(self):
        integration = GoogleSuiteIntegration()

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, "not valid json {{{", ""),
        ):
            result = await integration.run_command(GoogleSuiteCommand.CALENDAR_LIST)
            assert result.success is False
            assert "json" in result.error.lower() or "parse" in result.error.lower()

    async def test_run_command_handles_dict_output(self):
        """When gogcli returns a single JSON object instead of an array."""
        integration = GoogleSuiteIntegration()
        mock_output = json.dumps({"title": "Solo event", "start": "2026-02-16T10:00:00"})

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await integration.run_command(GoogleSuiteCommand.CALENDAR_LIST)
            assert result.success is True
            assert len(result.data) == 1
            assert result.data[0]["title"] == "Solo event"

    async def test_run_command_handles_scalar_output(self):
        """When gogcli returns a scalar JSON value (e.g., a count)."""
        integration = GoogleSuiteIntegration()
        mock_output = json.dumps(42)

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await integration.run_command(GoogleSuiteCommand.CALENDAR_LIST)
            assert result.success is True
            assert result.data == [{"value": 42}]

    async def test_run_command_with_extra_args(self):
        """Verify extra_args are passed to _exec_gogcli."""
        integration = GoogleSuiteIntegration()
        mock_output = json.dumps([])

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ) as mock_exec:
            await integration.run_command(
                GoogleSuiteCommand.CALENDAR_LIST,
                extra_args=["--max=5"],
            )
            mock_exec.assert_called_once_with(["cal", "events", "list", "--max=5"])

    async def test_run_command_nonzero_exit_no_stderr(self):
        """Error result when exit code is nonzero but stderr is empty."""
        integration = GoogleSuiteIntegration()

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(2, "", ""),
        ):
            result = await integration.run_command(GoogleSuiteCommand.GMAIL_LIST)
            assert result.success is False
            assert "2" in result.error  # Should mention exit code

    async def test_get_calendar_events(self):
        integration = GoogleSuiteIntegration()
        mock_output = json.dumps([{"title": "Lunch", "start": "2026-02-16T12:00:00"}])

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await integration.get_calendar_events()
            assert result.success is True
            assert result.data[0]["title"] == "Lunch"

    async def test_get_emails(self):
        integration = GoogleSuiteIntegration()
        mock_output = json.dumps(
            [
                {"subject": "Important update", "from": "boss@example.com"},
            ]
        )

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await integration.get_emails(max_results=5)
            assert result.success is True
            assert result.data[0]["subject"] == "Important update"

    async def test_get_contacts(self):
        integration = GoogleSuiteIntegration()
        mock_output = json.dumps([{"name": "Jane", "email": "jane@example.com"}])

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await integration.get_contacts()
            assert result.success is True
            assert result.data[0]["name"] == "Jane"

    async def test_get_tasks(self):
        integration = GoogleSuiteIntegration()
        mock_output = json.dumps([{"title": "Buy milk", "status": "needsAction"}])

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, mock_output, ""),
        ):
            result = await integration.get_tasks()
            assert result.success is True
            assert result.data[0]["title"] == "Buy milk"
            assert result.data[0]["status"] == "needsAction"


class TestGoogleSuiteErrorPaths:
    """Amendment 10: Dedicated error path tests."""

    async def test_exec_timeout(self):
        """Timeout during subprocess execution."""
        integration = GoogleSuiteIntegration()

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(1, "", "Command timed out after 30.0s"),
        ):
            result = await integration.run_command(GoogleSuiteCommand.CALENDAR_LIST)
            assert result.success is False
            assert "timed out" in result.error.lower()

    async def test_exec_binary_not_found(self):
        """FileNotFoundError during subprocess execution."""
        integration = GoogleSuiteIntegration()

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(1, "", "gogcli binary not found"),
        ):
            result = await integration.run_command(GoogleSuiteCommand.CALENDAR_LIST)
            assert result.success is False
            assert "not found" in result.error.lower()

    async def test_empty_json_array_is_valid(self):
        """Empty array from gogcli is a valid successful result."""
        integration = GoogleSuiteIntegration()

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, "[]", ""),
        ):
            result = await integration.run_command(GoogleSuiteCommand.TASKS_LIST)
            assert result.success is True
            assert result.data == []

    async def test_raw_output_preserved_on_error(self):
        """Raw output is preserved even on parse failure for debugging."""
        integration = GoogleSuiteIntegration()
        bad_output = "not valid json {{{"

        with patch(
            "vecna.integrations.google_suite.GoogleSuiteIntegration._exec_gogcli",
            new_callable=AsyncMock,
            return_value=(0, bad_output, ""),
        ):
            result = await integration.run_command(GoogleSuiteCommand.CALENDAR_LIST)
            assert result.raw_output == bad_output
