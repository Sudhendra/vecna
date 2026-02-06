from vecna.tools.permissions import (
    RiskTier,
    ToolPolicy,
    ToolPermissionManager,
    assess_code_risk,
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
