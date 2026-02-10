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
