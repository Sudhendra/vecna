import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class RiskTier(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class PolicyDecision:
    action: str
    reason: str


@dataclass
class ToolPolicy:
    default_action: str = "deny"
    allowlist: List[str] = field(default_factory=list)
    denylist: List[str] = field(default_factory=list)
    risk_actions: Dict[RiskTier, str] = field(
        default_factory=lambda: {
            RiskTier.LOW: "allow",
            RiskTier.MEDIUM: "ask",
            RiskTier.HIGH: "deny",
            RiskTier.CRITICAL: "deny",
        }
    )


class ToolPermissionManager:
    def __init__(self, policy: ToolPolicy):
        self.policy = policy

    def decide(self, tool_name: str, risk: RiskTier) -> PolicyDecision:
        """Return policy decision with allowlist precedence over denylist."""
        if tool_name in self.policy.allowlist:
            return PolicyDecision("allow", "allowlist")
        if tool_name in self.policy.denylist:
            return PolicyDecision("deny", "denylist")
        action = self.policy.risk_actions.get(risk, self.policy.default_action)
        return PolicyDecision(action, f"risk:{risk.value}")


def assess_code_risk(code: str) -> RiskTier:
    risky_imports = {"subprocess", "os", "socket", "requests", "urllib"}
    risky_functions = {"system", "popen", "run"}
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return RiskTier.MEDIUM

    risky_modules: set[str] = set()
    risky_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base_module = alias.name.split(".")[0]
                if base_module in risky_imports:
                    risky_modules.add(alias.asname or base_module)
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in risky_imports:
                for alias in node.names:
                    if alias.name in risky_functions:
                        risky_names.add(alias.asname or alias.name)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if (
                    node.func.attr in risky_functions
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id in risky_modules
                ):
                    return RiskTier.HIGH
            if isinstance(node.func, ast.Name):
                if node.func.id in risky_names:
                    return RiskTier.HIGH

    return RiskTier.LOW
