"""Tests for autonomy kill-switch persistence and audit behavior."""

from pathlib import Path

import pytest

from vecna.orchestrator.kill_switch import KillSwitch, KillSwitchActiveError


def test_kill_switch_persists_and_records_audit_events(tmp_path: Path):
    switch = KillSwitch(state_dir=tmp_path)

    assert switch.is_active() is False

    switch.kill("manual emergency stop")
    assert switch.is_active() is True

    reloaded = KillSwitch(state_dir=tmp_path)
    assert reloaded.is_active() is True

    reloaded.resume("manual recovery")
    assert reloaded.is_active() is False

    trail = reloaded.get_audit_trail()
    assert len(trail) == 2
    assert trail[0]["action"] == "kill"
    assert trail[0]["reason"] == "manual emergency stop"
    assert trail[1]["action"] == "resume"
    assert trail[1]["reason"] == "manual recovery"


def test_kill_switch_check_or_raise_raises_when_active(tmp_path: Path):
    switch = KillSwitch(state_dir=tmp_path)
    switch.kill("safety")

    with pytest.raises(KillSwitchActiveError, match="safety"):
        switch.check_or_raise()
