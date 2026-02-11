"""Session compaction and flush management."""

from dataclasses import dataclass
import json
from typing import Any, Dict, List, Optional

from vecna.adapters.base import BaseAdapter
from vecna.core.types import Belief, Fact
from vecna.memory.mirror import MemoryMirror
from vecna.memory.store import MemoryCompressor


def should_flush(current_tokens: int, limit: int, soft_threshold: int) -> bool:
    return (limit - current_tokens) <= soft_threshold


def estimate_token_count(text: str) -> int:
    """Estimate tokens as rounded-up characters per four."""
    if not text:
        return 0
    return (len(text) + 3) // 4


COMPACTION_PROMPT = """Analyze this conversation and extract:
1. session_summary: 2-3 sentence summary of what was discussed/accomplished
2. task_state: Current task, what's done, what's next, any blockers
3. new_facts: List of factual statements learned (with confidence 0-1)
4. new_beliefs: List of opinions/assessments formed (with confidence 0-1)
5. key_decisions: List of decisions made with rationale
6. open_questions: Unresolved questions that need follow-up

Return as JSON. Be concise. Only include genuinely new information,
not things already in MEMORY.md."""


@dataclass
class TaskState:
    current_task: str
    next_steps: str
    blockers: str


@dataclass
class FlushResult:
    session_summary: str
    task_state: TaskState
    new_facts: List[Fact]
    new_beliefs: List[Belief]
    key_decisions: List[str]
    open_questions: List[str]
    tokens_used: int = 0


class FlushManager:
    """Manages memory compaction triggers and execution."""

    def __init__(
        self,
        adapter: Optional[BaseAdapter],
        mirror: MemoryMirror,
        config: Any,
        token_threshold: Optional[int] = None,
    ):
        self.adapter = adapter
        self.mirror = mirror
        self.token_threshold = token_threshold or getattr(
            getattr(config, "memory", None),
            "flush_token_threshold",
            6000,
        )
        self._fallback = MemoryCompressor()

    def should_flush(self, conversation_tokens: int) -> bool:
        return conversation_tokens >= self.token_threshold

    async def flush_session_end(self, conversation: List[Dict[str, str]]) -> FlushResult:
        if self.adapter is None:
            return self._extractive_fallback(conversation)

        prompt = self._build_prompt(conversation)
        response = await self.adapter.generate(prompt)
        return self._parse_flush_response(response)

    async def flush_mid_session(self, conversation: List[Dict[str, str]]) -> FlushResult:
        if len(conversation) <= 2:
            return self._empty_result()

        start_idx = 0
        if conversation and conversation[0].get("role") == "system":
            content = conversation[0].get("content", "")
            if content.startswith("[Session context compressed:"):
                start_idx = 1

        flush_end = len(conversation) - 2
        if flush_end <= start_idx:
            return self._empty_result()

        segment = conversation[start_idx:flush_end]
        result = await self.flush_session_end(segment)
        if not result.session_summary:
            return self._empty_result()

        summary_block = {
            "role": "system",
            "content": f"[Session context compressed: {result.session_summary}]",
        }
        conversation[start_idx:flush_end] = [summary_block]
        return result

    def _build_prompt(self, conversation: List[Dict[str, str]]) -> str:
        lines = [COMPACTION_PROMPT, "\nConversation:\n"]
        for msg in conversation:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)

    def _parse_flush_response(self, response: str) -> FlushResult:
        try:
            payload = json.loads(response)
        except json.JSONDecodeError:
            return self._extractive_fallback([])

        task_state = payload.get("task_state") or {}
        return FlushResult(
            session_summary=payload.get("session_summary", ""),
            task_state=TaskState(
                current_task=task_state.get("current_task", ""),
                next_steps=task_state.get("next_steps", ""),
                blockers=task_state.get("blockers", ""),
            ),
            new_facts=[
                Fact(content=f.get("content", ""), confidence=f.get("confidence", 0.5))
                for f in payload.get("new_facts", [])
            ],
            new_beliefs=[
                Belief(content=b.get("content", ""), confidence=b.get("confidence", 0.5))
                for b in payload.get("new_beliefs", [])
            ],
            key_decisions=list(payload.get("key_decisions", []) or []),
            open_questions=list(payload.get("open_questions", []) or []),
            tokens_used=payload.get("tokens_used", 0),
        )

    def _extractive_fallback(self, conversation: List[Dict[str, str]]) -> FlushResult:
        summary = " ".join(msg.get("content", "") for msg in conversation if msg.get("content"))
        if summary:
            summary = summary[:200]
        return FlushResult(
            session_summary=summary,
            task_state=TaskState(current_task="", next_steps="", blockers=""),
            new_facts=[],
            new_beliefs=[],
            key_decisions=[],
            open_questions=[],
            tokens_used=estimate_token_count(summary),
        )

    def _empty_result(self) -> FlushResult:
        return FlushResult(
            session_summary="",
            task_state=TaskState(current_task="", next_steps="", blockers=""),
            new_facts=[],
            new_beliefs=[],
            key_decisions=[],
            open_questions=[],
            tokens_used=0,
        )
