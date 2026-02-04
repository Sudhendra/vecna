import re
from typing import Dict, List

_STEP_PATTERN = re.compile(r"^E\d+:\s*(?P<tool>\w+)\[(?P<input>.*)\]$")


def parse_rewoo_plan(plan: str) -> List[Dict[str, str]]:
    steps: List[Dict[str, str]] = []
    for line in plan.splitlines():
        match = _STEP_PATTERN.match(line.strip())
        if match:
            steps.append(
                {
                    "tool": match.group("tool"),
                    "input": match.group("input"),
                }
            )
    return steps
