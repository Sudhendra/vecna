from vecna.tools.permissions import (
    RiskTier,
    ToolPolicy,
    ToolPermissionManager,
    assess_code_risk,
    assess_tool_risk,
)


def test_policy_allowlist_wins():
    policy = ToolPolicy(
        allowlist=["python_exec"],
        denylist=["python_exec"],
        default_action="deny",
    )
    mgr = ToolPermissionManager(policy)
    decision = mgr.decide("python_exec", risk=RiskTier.LOW)
    assert decision.action == "allow"


def test_assess_code_risk_high_for_subprocess():
    code = "import subprocess\nsubprocess.run(['ls'])"
    assert assess_code_risk(code) in (RiskTier.HIGH, RiskTier.CRITICAL)


def test_assess_code_risk_high_for_imported_name_call():
    code = "from subprocess import run\nrun(['ls'])"
    assert assess_code_risk(code) in (RiskTier.HIGH, RiskTier.CRITICAL)


def test_assess_code_risk_low_for_unrelated_run_attribute():
    code = """class Runner:
    def run(self):
        return 0

runner = Runner()
runner.run()
"""
    assert assess_code_risk(code) == RiskTier.LOW


def test_assess_tool_risk_python_exec_uses_code_assessment():
    code = "import os\nos.system('x')"
    assert assess_tool_risk("python_exec", {"code": code}) == RiskTier.HIGH


def test_assess_tool_risk_http_request_method_sensitive():
    assert assess_tool_risk("http_request", {"method": "GET"}) == RiskTier.LOW
    assert assess_tool_risk("http_request", {"method": "HEAD"}) == RiskTier.LOW
    assert assess_tool_risk("http_request", {"method": "POST"}) == RiskTier.MEDIUM


def test_assess_tool_risk_fs_tools_are_medium():
    assert assess_tool_risk("fs_read", {"path": "/tmp/x"}) == RiskTier.MEDIUM


def test_assess_tool_risk_default_low():
    assert assess_tool_risk("memory_get", {}) == RiskTier.LOW


def test_assess_tool_risk_non_dict_args_returns_medium():
    assert assess_tool_risk("http_request", "not-a-dict") == RiskTier.MEDIUM
