"""E2E coverage for tool approval CLI commands."""

from click.testing import CliRunner

from vecna.cli.main import cli
from vecna.tools.approvals import ApprovalStore


def test_tools_group_help_lists_pending_approve_and_deny():
    runner = CliRunner()

    result = runner.invoke(cli, ["tools", "--help"])

    assert result.exit_code == 0
    assert "pending" in result.output
    assert "approve" in result.output
    assert "deny" in result.output


def test_tools_pending_approve_and_deny_flow(tmp_path, monkeypatch):
    approvals_path = tmp_path / "approvals.jsonl"
    monkeypatch.setenv("VECNA_APPROVALS_PATH", str(approvals_path))
    store = ApprovalStore()
    request_one = store.request_approval("http_request", {"url": "https://example.com"})
    request_two = store.request_approval("python_exec", {"code": "print('ok')"})

    runner = CliRunner()
    pending_before = runner.invoke(cli, ["tools", "pending"])
    assert pending_before.exit_code == 0
    assert request_one.request_id in pending_before.output
    assert request_two.request_id in pending_before.output

    approve_result = runner.invoke(cli, ["tools", "approve", request_one.request_id])
    deny_result = runner.invoke(cli, ["tools", "deny", request_two.request_id])
    assert approve_result.exit_code == 0
    assert deny_result.exit_code == 0

    pending_after = runner.invoke(cli, ["tools", "pending"])
    assert pending_after.exit_code == 0
    assert request_one.request_id not in pending_after.output
    assert request_two.request_id not in pending_after.output
