"""
Unit tests for tool config defaults.
"""

from typing import Any, cast

from vecna.config.schema import VecnaConfig, create_default_config


def test_config_has_tool_policy_defaults():
    cfg = create_default_config()

    assert hasattr(cfg, "tool_policy")
    assert cfg.tool_policy.default_action in {"allow", "deny"}


def test_memory_config_has_identity_defaults():
    cfg = create_default_config()

    assert cfg.memory.vector_weight == 0.7
    assert cfg.memory.text_weight == 0.3
    assert cfg.memory.flush_token_threshold == 6000
    assert cfg.memory.markdown_chunk_tokens == 400


def test_config_has_workspace_dir_default():
    cfg = create_default_config()

    assert cfg.workspace_dir == "~/.vecna"


def test_config_has_rewoo_defaults():
    cfg = create_default_config()

    assert cfg.enable_rewoo_planning is False
    assert cfg.rewoo_max_steps == 8
    assert cfg.rewoo_retry_limit == 1
    assert cfg.rewoo_backoff_base_seconds == 0.25
    assert cfg.rewoo_max_artifact_chars == 4000
    assert cfg.rewoo_min_task_words == 8
    assert cfg.rewoo_force is False


def test_rewoo_eligibility_fields_round_trip():
    cfg = VecnaConfig(rewoo_min_task_words=3, rewoo_force=True)

    serialized = cfg.to_dict()
    round_tripped = VecnaConfig.from_dict(serialized)

    assert serialized["rewoo_min_task_words"] == 3
    assert serialized["rewoo_force"] is True
    assert round_tripped.rewoo_min_task_words == 3
    assert round_tripped.rewoo_force is True


def test_config_has_tooling_and_autonomy_flags():
    cfg = create_default_config()

    assert cfg.enable_web_tools is False
    assert cfg.enable_fs_tools is False
    assert cfg.enable_autonomy_heartbeat is False
    assert cfg.tool_quota_per_session == 0
    assert cfg.tool_quota_per_tool == 0
    assert cfg.tool_allowed_fs_roots == ["~/.vecna"]


def test_from_dict_normalizes_tool_allowed_fs_roots():
    cfg = VecnaConfig.from_dict({"tool_allowed_fs_roots": ["/tmp", 123, None, "~/work"]})

    assert cfg.tool_allowed_fs_roots == ["/tmp", "~/work"]


def test_from_dict_defaults_tool_allowed_fs_roots_for_invalid_type():
    cfg = VecnaConfig.from_dict({"tool_allowed_fs_roots": cast(Any, 123)})

    assert cfg.tool_allowed_fs_roots == ["~/.vecna"]


def test_tool_allowed_fs_roots_round_trip_uses_normalized_values():
    cfg = VecnaConfig(tool_allowed_fs_roots=cast(Any, ["/tmp", 123, "/work"]))

    serialized = cfg.to_dict()
    round_tripped = VecnaConfig.from_dict(serialized)

    assert serialized["tool_allowed_fs_roots"] == ["/tmp", "/work"]
    assert round_tripped.tool_allowed_fs_roots == ["/tmp", "/work"]
