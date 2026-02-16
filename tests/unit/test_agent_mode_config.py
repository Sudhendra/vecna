"""Unit tests for agent mode configuration handling."""

import json
import logging
from typing import Any, cast

from vecna.config import loader
from vecna.config.schema import AgentMode, VecnaConfig


def test_default_agent_mode():
    cfg = VecnaConfig()
    assert cfg.agent_mode == AgentMode.assistant


def test_agent_mode_parsing():
    cfg = VecnaConfig(agent_mode=AgentMode.explorer)
    assert cfg.agent_mode == AgentMode.explorer


def test_invalid_agent_mode_defaults_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="vecna.config"):
        cfg = VecnaConfig.from_dict({"agent_mode": "invalid"})

    assert cfg.agent_mode == AgentMode.assistant
    assert any("Invalid agent_mode" in record.getMessage() for record in caplog.records)


def test_non_string_agent_mode_in_from_dict_defaults_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger="vecna.config"):
        cfg = VecnaConfig.from_dict({"agent_mode": 123})

    assert cfg.agent_mode == AgentMode.assistant
    assert any("Invalid agent_mode" in record.getMessage() for record in caplog.records)


def test_invalid_agent_mode_serialization_defaults_and_warns(caplog):
    cfg = VecnaConfig(agent_mode=cast(Any, "invalid"))

    with caplog.at_level(logging.WARNING, logger="vecna.config"):
        serialized = cfg.to_dict()

    assert serialized["agent_mode"] == AgentMode.assistant.value
    assert any("Invalid agent_mode" in record.getMessage() for record in caplog.records)


def test_non_string_agent_mode_serialization_defaults_and_warns(caplog):
    cfg = VecnaConfig(agent_mode=cast(Any, 123))

    with caplog.at_level(logging.WARNING, logger="vecna.config"):
        serialized = cfg.to_dict()

    assert serialized["agent_mode"] == AgentMode.assistant.value
    assert any("Invalid agent_mode" in record.getMessage() for record in caplog.records)


def test_loader_preserves_agent_mode_from_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"config_version": 2, "agent_mode": "explorer"}))

    monkeypatch.setattr(loader, "get_config_path", lambda: config_path)
    loader._cached_config = None

    cfg = loader.load_config(force_reload=True)

    assert cfg.agent_mode == AgentMode.explorer


def test_from_dict_parses_rewoo_settings():
    cfg = VecnaConfig.from_dict(
        {
            "enable_rewoo_planning": True,
            "rewoo_max_steps": 12,
            "rewoo_retry_limit": 3,
            "rewoo_backoff_base_seconds": 0.5,
            "rewoo_max_artifact_chars": 1024,
            "rewoo_min_task_words": 4,
            "rewoo_force": True,
        }
    )

    assert cfg.enable_rewoo_planning is True
    assert cfg.rewoo_max_steps == 12
    assert cfg.rewoo_retry_limit == 3
    assert cfg.rewoo_backoff_base_seconds == 0.5
    assert cfg.rewoo_max_artifact_chars == 1024
    assert cfg.rewoo_min_task_words == 4
    assert cfg.rewoo_force is True


def test_to_dict_includes_rewoo_settings():
    cfg = VecnaConfig(
        enable_rewoo_planning=True,
        rewoo_max_steps=10,
        rewoo_retry_limit=2,
        rewoo_backoff_base_seconds=0.4,
        rewoo_max_artifact_chars=2048,
        rewoo_min_task_words=6,
        rewoo_force=True,
    )

    serialized = cfg.to_dict()

    assert serialized["enable_rewoo_planning"] is True
    assert serialized["rewoo_max_steps"] == 10
    assert serialized["rewoo_retry_limit"] == 2
    assert serialized["rewoo_backoff_base_seconds"] == 0.4
    assert serialized["rewoo_max_artifact_chars"] == 2048
    assert serialized["rewoo_min_task_words"] == 6
    assert serialized["rewoo_force"] is True
