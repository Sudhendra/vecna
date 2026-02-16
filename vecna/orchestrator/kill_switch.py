"""Persistent kill switch for autonomy loop safety control."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


class KillSwitchActiveError(RuntimeError):
    """Raised when autonomy is blocked by an active kill switch."""


class KillSwitch:
    """Stores kill-switch state on disk and records an audit trail."""

    def __init__(self, state_dir: Path):
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.state_dir / "kill_switch_state.json"
        self.audit_path = self.state_dir / "kill_switch_audit.jsonl"

    def kill(self, reason: str) -> None:
        self._write_state(active=True, reason=reason)
        self._append_audit_event(action="kill", reason=reason)

    def resume(self, reason: str) -> None:
        self._write_state(active=False, reason=reason)
        self._append_audit_event(action="resume", reason=reason)

    def is_active(self) -> bool:
        state = self._read_state()
        return bool(state.get("active", False))

    def check_or_raise(self) -> None:
        state = self._read_state()
        if bool(state.get("active", False)):
            reason = str(state.get("reason", "unspecified"))
            raise KillSwitchActiveError(f"Kill switch is active: {reason}")

    def get_audit_trail(self) -> List[Dict[str, Any]]:
        if not self.audit_path.exists():
            return []

        events: List[Dict[str, Any]] = []
        for line in self.audit_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def _read_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return self._default_state()

        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return self._default_state()

        if not isinstance(data, dict):
            return self._default_state()
        return data

    def _write_state(self, active: bool, reason: str) -> None:
        payload = {
            "active": bool(active),
            "reason": reason,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.state_path.write_text(json.dumps(payload), encoding="utf-8")

    def _append_audit_event(self, action: str, reason: str) -> None:
        event = {
            "action": action,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    def _default_state(self) -> Dict[str, Any]:
        return {
            "active": False,
            "reason": "",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
