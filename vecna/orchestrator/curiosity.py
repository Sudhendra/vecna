"""Curiosity engine for generating structured exploration goals."""

from dataclasses import dataclass
from typing import Any, Dict, List, Union

from vecna.core.types import Contradiction, OpenQuestion


@dataclass
class CuriosityGoal:
    """A structured curiosity goal generated from hive uncertainty."""

    content: str
    priority: str
    source: str

    def to_legacy_dict(self) -> Dict[str, str]:
        """Convert to the legacy dictionary goal structure."""

        return {
            "goal": f"explore {self.content}",
            "priority": self.priority,
            "source": self.source,
        }


class CuriosityEngine:
    """Build curiosity goals from open questions and contradictions."""

    def from_open_questions(
        self, questions: List[Union[OpenQuestion, Dict[str, Any]]]
    ) -> List[CuriosityGoal]:
        """Create curiosity goals from unresolved open questions."""

        goals: List[CuriosityGoal] = []
        for item in questions:
            question = self._extract_question_content(item)
            if not question:
                continue

            goals.append(
                CuriosityGoal(
                    content=question,
                    priority=self._extract_priority(item, default="medium"),
                    source="open_question",
                )
            )
        return goals

    def from_contradictions(
        self, contradictions: List[Union[Contradiction, Dict[str, Any]]]
    ) -> List[CuriosityGoal]:
        """Create curiosity goals from contradictions between two statements."""

        goals: List[CuriosityGoal] = []
        for item in contradictions:
            contradiction_content = self._extract_contradiction_content(item)
            if not contradiction_content:
                continue

            goals.append(
                CuriosityGoal(
                    content=contradiction_content,
                    priority=self._extract_priority(item, default="high"),
                    source="contradiction",
                )
            )
        return goals

    def from_contradictions_legacy(
        self, contradictions: List[Union[Contradiction, Dict[str, Any]]]
    ) -> List[Dict[str, str]]:
        """Backward-compatible adapter that returns legacy goal dictionaries."""

        return [goal.to_legacy_dict() for goal in self.from_contradictions(contradictions)]

    def _extract_question_content(self, item: Union[OpenQuestion, Dict[str, Any]]) -> str:
        if isinstance(item, OpenQuestion):
            return str(item.question or "").strip()
        return str(item.get("question") or "").strip()

    def _extract_contradiction_content(self, item: Union[Contradiction, Dict[str, Any]]) -> str:
        if isinstance(item, Contradiction):
            item_a = str(item.item_a_content or "").strip()
            item_b = str(item.item_b_content or "").strip()
            if item_a and item_b:
                return f"contradiction: {item_a} vs {item_b}"
            return ""

        item_a = str(item.get("item_a_content") or "").strip()
        item_b = str(item.get("item_b_content") or "").strip()
        if item_a and item_b:
            return f"contradiction: {item_a} vs {item_b}"
        if "item_a_content" in item or "item_b_content" in item:
            return ""

        # Legacy callers used a single `content` field.
        return str(item.get("content") or "").strip()

    def _extract_priority(
        self, item: Union[OpenQuestion, Contradiction, Dict[str, Any]], default: str
    ) -> str:
        if isinstance(item, OpenQuestion):
            return self._normalize_priority(item.priority, default=default)
        if isinstance(item, Contradiction):
            return default
        return self._normalize_priority(item.get("priority"), default=default)

    def _normalize_priority(self, value: Any, default: str) -> str:
        priority = str(value or "").strip()
        return priority or default
