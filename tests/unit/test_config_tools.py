"""
Unit tests for tool config defaults.
"""

from vecna.config.schema import create_default_config


def test_config_has_tool_policy_defaults():
    cfg = create_default_config()

    assert hasattr(cfg, "tool_policy")
    assert cfg.tool_policy.default_action in {"allow", "deny"}
