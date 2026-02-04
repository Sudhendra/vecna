from click.testing import CliRunner

from vecna.cli.main import cli
from vecna.tools.approvals import ApprovalRequest, ApprovalStore


def test_tools_pending_empty():
    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "pending"])
    assert result.exit_code == 0


def test_tools_pending_shows_saved_requests(tmp_path, monkeypatch):
    approvals_path = tmp_path / "approvals.json"
    monkeypatch.setenv("VECNA_APPROVALS_PATH", str(approvals_path))

    store = ApprovalStore()
    store.add_request(ApprovalRequest(request_id="req-1", tool_name="search", status="pending"))

    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "pending"])

    assert result.exit_code == 0
    assert "req-1 search pending" in result.output


def test_tools_approve_updates_status(tmp_path, monkeypatch):
    approvals_path = tmp_path / "approvals.json"
    monkeypatch.setenv("VECNA_APPROVALS_PATH", str(approvals_path))

    store = ApprovalStore()
    store.add_request(ApprovalRequest(request_id="req-2", tool_name="exec", status="pending"))

    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "approve", "req-2"])

    assert result.exit_code == 0
    updated = ApprovalStore().get_request("req-2")
    assert updated is not None
    assert updated.status == "approved"


def test_tools_approve_missing_request_fails(tmp_path, monkeypatch):
    approvals_path = tmp_path / "approvals.json"
    monkeypatch.setenv("VECNA_APPROVALS_PATH", str(approvals_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "approve", "missing"])

    assert result.exit_code != 0
    assert "not found" in result.output.lower()
