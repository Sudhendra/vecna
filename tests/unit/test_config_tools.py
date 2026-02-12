"""
Unit tests for tool config defaults.
"""

from vecna.config.schema import create_default_config


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
