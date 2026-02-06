import json
import os
from pathlib import Path

from vecna.tools.approvals import ApprovalStore
from vecna.tools.audit import ToolAuditEvent, ToolAuditLogger


def test_audit_logger_writes_event(tmp_path: Path):
    log_path = tmp_path / "audit.jsonl"
    logger = ToolAuditLogger(log_path=log_path)
    event = ToolAuditEvent(tool_name="python_exec", action="allow", risk_tier="low")
    logger.log_event(event)
    assert log_path.read_text().strip().startswith("{")


def test_approval_store_round_trip(tmp_path: Path):
    store = ApprovalStore(path=tmp_path / "approvals.jsonl")
    req = store.request_approval(tool_name="python_exec", args={"code": "print(1)"})
    pending = store.get_pending()
    assert pending[0].request_id == req.request_id
    assert store.update_status(req.request_id, "approved") is True
    assert store.get_pending() == []


def test_approval_store_get_pending_skips_invalid_lines(tmp_path: Path):
    path = tmp_path / "approvals.jsonl"
    valid = {
        "request_id": "req-1",
        "tool_name": "python_exec",
        "args": {},
        "status": "pending",
        "created_at": "2024-01-01T00:00:00",
    }
    approved = {
        "request_id": "req-2",
        "tool_name": "python_exec",
        "args": {},
        "status": "approved",
        "created_at": "2024-01-01T00:00:00",
    }
    path.write_text(
        "\n".join(["", "not json", json.dumps(valid), json.dumps(approved), ""]) + "\n",
        encoding="utf-8",
    )
    store = ApprovalStore(path=path)
    pending = store.get_pending()
    assert [entry.request_id for entry in pending] == ["req-1"]


def test_approval_store_update_status_skips_invalid_lines(tmp_path: Path):
    path = tmp_path / "approvals.jsonl"
    request = {
        "request_id": "req-1",
        "tool_name": "python_exec",
        "args": {},
        "status": "pending",
        "created_at": "2024-01-01T00:00:00",
    }
    path.write_text(
        "\n".join(["not json", json.dumps(request), ""]) + "\n",
        encoding="utf-8",
    )
    store = ApprovalStore(path=path)
    assert store.update_status("req-1", "approved") is True
    updated = None
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("request_id") == "req-1":
            updated = data
    assert updated is not None
    assert updated["status"] == "approved"


def test_approval_store_update_status_no_rewrite_on_missing_id(tmp_path: Path):
    path = tmp_path / "approvals.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "request_id": "req-1",
                        "tool_name": "python_exec",
                        "args": {},
                        "status": "pending",
                        "created_at": "2024-01-01T00:00:00",
                    }
                ),
                "not json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    os.utime(path, (1, 1))
    before_stat = path.stat()
    store = ApprovalStore(path=path)
    assert store.update_status("missing", "approved") is False
    after_stat = path.stat()
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns
