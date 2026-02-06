from vecna.orchestrator.rewoo import parse_rewoo_plan


def test_parse_rewoo_plan():
    plan = "Plan: need info\nE1: Search[foo]"
    steps = parse_rewoo_plan(plan)
    assert steps[0]["tool"] == "Search"
