import json

from click.testing import CliRunner

from vecna.cli.main import cli
from vecna.tools.approvals import ApprovalStore


def test_tools_pending_empty(tmp_path, monkeypatch):
    approvals_path = tmp_path / "approvals.jsonl"
    monkeypatch.setenv("VECNA_APPROVALS_PATH", str(approvals_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "pending"])

    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_tools_pending_shows_saved_requests(tmp_path, monkeypatch):
    approvals_path = tmp_path / "approvals.jsonl"
    monkeypatch.setenv("VECNA_APPROVALS_PATH", str(approvals_path))

    store = ApprovalStore()
    request = store.request_approval("search", {"query": "a"})

    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "pending"])

    assert result.exit_code == 0
    assert f"{request.request_id} {request.tool_name} pending" in result.output


def test_tools_approve_updates_status(tmp_path, monkeypatch):
    approvals_path = tmp_path / "approvals.jsonl"
    monkeypatch.setenv("VECNA_APPROVALS_PATH", str(approvals_path))

    store = ApprovalStore()
    request = store.request_approval("exec", {"code": "print('hi')"})

    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "approve", request.request_id])

    assert result.exit_code == 0

    entries = approvals_path.read_text(encoding="utf-8").splitlines()
    payloads = [json.loads(line) for line in entries if line.strip()]
    updated = next(item for item in payloads if item["request_id"] == request.request_id)
    assert updated["status"] == "approved"


def test_tools_approve_missing_request_fails(tmp_path, monkeypatch):
    approvals_path = tmp_path / "approvals.jsonl"
    monkeypatch.setenv("VECNA_APPROVALS_PATH", str(approvals_path))

    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "approve", "missing"])

    assert result.exit_code != 0
    assert "not found" in result.output.lower()


def test_tools_deny_updates_status(tmp_path, monkeypatch):
    approvals_path = tmp_path / "approvals.jsonl"
    monkeypatch.setenv("VECNA_APPROVALS_PATH", str(approvals_path))

    store = ApprovalStore()
    request = store.request_approval("exec", {"code": "print('hi')"})

    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "deny", request.request_id])

    assert result.exit_code == 0

    entries = approvals_path.read_text(encoding="utf-8").splitlines()
    payloads = [json.loads(line) for line in entries if line.strip()]
    updated = next(item for item in payloads if item["request_id"] == request.request_id)
    assert updated["status"] == "denied"
