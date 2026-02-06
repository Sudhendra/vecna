from vecna.tools.permissions import PolicyDecision, RiskTier, ToolPermissionManager, ToolPolicy


def test_tool_permission_manager_allowlist_overrides_denylist():
    policy = ToolPolicy(allowlist=["safe"], denylist=["safe"])
    manager = ToolPermissionManager(policy)

    decision = manager.decide("safe", RiskTier.HIGH)

    assert decision == PolicyDecision("allow", "allowlist")


def test_tool_permission_manager_denies_by_default_action():
    policy = ToolPolicy(default_action="deny", risk_actions={})
    manager = ToolPermissionManager(policy)

    decision = manager.decide("unknown", RiskTier.LOW)

    assert decision.action == "deny"
    assert decision.reason == "risk:low"


def test_tool_permission_manager_uses_risk_actions():
    policy = ToolPolicy(risk_actions={RiskTier.MEDIUM: "ask"})
    manager = ToolPermissionManager(policy)

    decision = manager.decide("python_exec", RiskTier.MEDIUM)

    assert decision == PolicyDecision("ask", "risk:medium")


def test_tool_permission_manager_denies_explicit_denylist():
    policy = ToolPolicy(denylist=["python_exec"])
    manager = ToolPermissionManager(policy)

    decision = manager.decide("python_exec", RiskTier.LOW)

    assert decision == PolicyDecision("deny", "denylist")
