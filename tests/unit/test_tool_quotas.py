"""Unit tests for tool execution quotas."""

from vecna.tools.quotas import QuotaConfig, ToolQuotaManager


def test_quota_manager_blocks_after_per_session_limit() -> None:
    manager = ToolQuotaManager(QuotaConfig(per_session=2, per_tool=0))

    assert manager.can_execute("session-1", "echo") is True
    manager.record("session-1", "echo")
    assert manager.can_execute("session-1", "echo") is True
    manager.record("session-1", "math")

    assert manager.can_execute("session-1", "echo") is False


def test_quota_manager_blocks_after_per_tool_limit() -> None:
    manager = ToolQuotaManager(QuotaConfig(per_session=0, per_tool=1))

    assert manager.can_execute("session-1", "echo") is True
    manager.record("session-1", "echo")

    assert manager.can_execute("session-1", "echo") is False
    assert manager.can_execute("session-1", "math") is True


def test_quota_manager_unlimited_config_permits_calls() -> None:
    manager = ToolQuotaManager(QuotaConfig(per_session=0, per_tool=0))

    for _ in range(100):
        assert manager.can_execute("session-1", "echo") is True
        manager.record("session-1", "echo")
