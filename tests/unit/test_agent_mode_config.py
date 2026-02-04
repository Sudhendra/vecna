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


def test_invalid_agent_mode_serialization_defaults_and_warns(caplog):
    cfg = VecnaConfig(agent_mode=cast(Any, "invalid"))

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
