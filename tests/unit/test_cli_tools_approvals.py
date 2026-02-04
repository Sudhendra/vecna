import logging
import os

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


def test_store_warns_on_invalid_json(tmp_path, caplog):
    approvals_path = tmp_path / "approvals.json"
    approvals_path.write_text("{not: valid}", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="vecna.approvals"):
        store = ApprovalStore(path=approvals_path)

    assert store.get_pending() == []
    assert any(approvals_path.as_posix() in record.message for record in caplog.records)


def test_store_uses_atomic_replace_on_save(tmp_path, monkeypatch):
    approvals_path = tmp_path / "approvals.json"
    calls = {"count": 0}
    original_replace = os.replace

    def fake_replace(src, dst):
        calls["count"] += 1
        original_replace(src, dst)

    monkeypatch.setattr("vecna.tools.approvals.os.replace", fake_replace)

    store = ApprovalStore(path=approvals_path)
    store.add_request(ApprovalRequest(request_id="req-3", tool_name="search", status="pending"))

    assert calls["count"] >= 1
