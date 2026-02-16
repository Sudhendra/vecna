"""Unit tests for the curiosity engine."""

from vecna.core.types import Contradiction, OpenQuestion
from vecna.orchestrator.curiosity import CuriosityEngine, CuriosityGoal


def test_curiosity_uses_open_question_question_field():
    engine = CuriosityEngine()

    question = OpenQuestion(question="Why does model A and model B disagree on X?")
    goals = engine.from_open_questions([question])

    assert goals
    assert isinstance(goals[0], CuriosityGoal)
    assert goals[0].content == question.question
    assert goals[0].priority == "medium"
    assert goals[0].source == "open_question"


def test_curiosity_uses_contradiction_content_fields():
    engine = CuriosityEngine()

    contradiction = Contradiction(item_a_content="Statement A", item_b_content="Statement B")
    goals = engine.from_contradictions([contradiction])

    assert goals
    assert isinstance(goals[0], CuriosityGoal)
    assert "Statement A" in goals[0].content
    assert "Statement B" in goals[0].content
    assert goals[0].priority == "high"
    assert goals[0].source == "contradiction"


def test_curiosity_goal_legacy_adapter_keeps_simple_behavior():
    engine = CuriosityEngine()

    goals = engine.from_contradictions_legacy([{"content": "X vs Y", "confidence": 0.4}])

    assert goals and "explore" in goals[0]["goal"]


def test_curiosity_skips_none_and_blank_open_questions_safely():
    engine = CuriosityEngine()

    goals = engine.from_open_questions(
        [
            OpenQuestion(question=None),
            OpenQuestion(question="   "),
            {"question": None},
            {"question": "  "},
        ]
    )

    assert goals == []


def test_curiosity_skips_invalid_contradiction_pairs_with_none_blank_fields():
    engine = CuriosityEngine()

    goals = engine.from_contradictions(
        [
            Contradiction(item_a_content=None, item_b_content="Statement B"),
            Contradiction(item_a_content="Statement A", item_b_content=None),
            {"item_a_content": None, "item_b_content": "Statement B"},
            {"item_a_content": "Statement A", "item_b_content": "  "},
        ]
    )

    assert goals == []


def test_curiosity_legacy_dict_priority_none_or_blank_falls_back_to_default():
    engine = CuriosityEngine()

    question_goals = engine.from_open_questions(
        [
            {"question": "What is uncertain?", "priority": None},
            {"question": "Where is the gap?", "priority": "  "},
        ]
    )
    contradiction_goals = engine.from_contradictions(
        [
            {"item_a_content": "A", "item_b_content": "B", "priority": None},
            {"item_a_content": "C", "item_b_content": "D", "priority": "   "},
        ]
    )

    assert [goal.priority for goal in question_goals] == ["medium", "medium"]
    assert [goal.priority for goal in contradiction_goals] == ["high", "high"]
