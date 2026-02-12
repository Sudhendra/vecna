import pytest

from vecna.orchestrator.rewoo import RewooPlan, parse_rewoo_plan


def test_parse_rewoo_plan_builds_typed_plan():
    plan_text = """Plan: gather data
E1: memory_search[python dataclasses]
E2: python_exec[print('summary:' + "#E1")]
Final: Use #E1 and #E2 to answer
"""

    plan = parse_rewoo_plan(plan_text)

    assert isinstance(plan, RewooPlan)
    assert plan.goal == "gather data"
    assert len(plan.steps) == 2
    assert plan.steps[0].step_id == "E1"
    assert plan.steps[0].tool_name == "memory_search"
    assert plan.steps[1].step_id == "E2"
    assert plan.steps[1].tool_name == "python_exec"
    assert plan.final_prompt_template == "Use #E1 and #E2 to answer"


def test_parse_rewoo_plan_rejects_unknown_lines():
    plan_text = """Plan: gather data
E1: memory_search[python dataclasses]
This line is not valid ReWOO syntax
Final: done
"""

    with pytest.raises(ValueError, match="Invalid ReWOO line"):
        parse_rewoo_plan(plan_text)


def test_parse_rewoo_plan_rejects_forward_reference():
    plan_text = """Plan: gather data
E1: python_exec[print(#E2)]
E2: memory_search[topic]
Final: done
"""

    with pytest.raises(ValueError, match="forward reference"):
        parse_rewoo_plan(plan_text)


def test_parse_rewoo_plan_rejects_unknown_final_reference():
    plan_text = """Plan: gather data
E1: memory_search[topic]
Final: summarize #E9
"""

    with pytest.raises(ValueError, match="Final template references unknown step"):
        parse_rewoo_plan(plan_text)
