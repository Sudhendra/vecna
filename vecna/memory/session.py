"""Session lifecycle management for memory/identity context."""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional
import uuid
import logging

from vecna.config.schema import VecnaConfig
from vecna.memory.flush import FlushManager, estimate_token_count
from vecna.memory.mirror import MemoryMirror
from vecna.memory.pg_store import MemoryItem

logger = logging.getLogger("vecna.memory.session")


@dataclass
class SessionContext:
    soul: str
    working: str
    daily_log: str
    relevant_memory: str
    session_id: str


class SessionManager:
    """Manages session lifecycle: start, end, mid-session checks."""

    def __init__(self, mirror: MemoryMirror, flush_mgr: FlushManager, config: VecnaConfig):
        self.mirror = mirror
        self.flush_mgr = flush_mgr
        self.config = config
        self.session_id = str(uuid.uuid4())
        self.started_at: Optional[datetime] = None

    async def start_session(self, initial_query: Optional[str] = None) -> SessionContext:
        self.started_at = datetime.utcnow()

        soul = self._read_file("SOUL.md")
        working = self._read_file("WORKING.md")
        daily_log = self._read_file(f"memory/{date.today().isoformat()}.md")

        await self.mirror.index_markdown_files()

        relevant_memory = ""
        if initial_query and self.mirror.pg_store is not None:
            chunks = self.mirror.pg_store.search(
                initial_query,
                top_k=5,
                hybrid=True,
                vector_weight=self.config.memory.vector_weight,
                text_weight=self.config.memory.text_weight,
            )
            relevant_memory = self._format_memory_results(chunks)

        return SessionContext(
            soul=soul,
            working=working,
            daily_log=daily_log,
            relevant_memory=relevant_memory,
            session_id=self.session_id,
        )

    async def end_session(self, conversation: List[Dict[str, str]]) -> None:
        result = await self.flush_mgr.flush_session_end(conversation)

        await self.mirror.append_daily_log(result.session_summary, datetime.utcnow())
        await self.mirror.update_working(
            result.task_state.current_task,
            result.task_state.next_steps,
            result.task_state.blockers,
        )

        promotable_facts = [f for f in result.new_facts if f.confidence > 0.7]
        promotable_beliefs = [b for b in result.new_beliefs if b.confidence > 0.7]
        if promotable_facts or promotable_beliefs or result.key_decisions or result.open_questions:
            await self.mirror.promote_to_memory(
                promotable_facts,
                promotable_beliefs,
                key_decisions=result.key_decisions,
                open_questions=result.open_questions,
            )

        await self.mirror.extract_facts_to_pg(result.new_facts, result.new_beliefs)
        await self.mirror.index_markdown_files()

        if self.mirror.pg_store is not None and self.started_at is not None:
            ended_at = datetime.utcnow()
            self.mirror.pg_store.record_session(
                session_id=self.session_id,
                started_at=self.started_at,
                ended_at=ended_at,
                summary=result.session_summary,
                tokens_used=result.tokens_used,
            )

    async def maybe_flush_mid_session(self, conversation: List[Dict[str, str]]) -> Optional[str]:
        tokens = sum(estimate_token_count(msg.get("content", "")) for msg in conversation)
        if not self.flush_mgr.should_flush(tokens):
            return None

        result = await self.flush_mgr.flush_mid_session(conversation)
        if not result.session_summary:
            return None

        await self.mirror.append_daily_log(result.session_summary, datetime.utcnow())
        await self.mirror.extract_facts_to_pg(result.new_facts, result.new_beliefs)
        logger.info("Mid-session flush completed")
        return result.session_summary

    def format_context(self, context: SessionContext) -> str:
        return (
            "[SOUL — Who I Am]\n"
            f"{context.soul}\n\n"
            "[WORKING — Current State]\n"
            f"{context.working}\n\n"
            "[TODAY'S LOG]\n"
            f"{context.daily_log}\n\n"
            "[RELEVANT MEMORY]\n"
            f"{context.relevant_memory}\n"
        )

    def _read_file(self, relative_path: str) -> str:
        path = Path(self.mirror.workspace_dir) / relative_path
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _format_memory_results(self, results: List[tuple[MemoryItem, float]]) -> str:
        lines = []
        for item, score in results:
            lines.append(f"- [{item.item_type}][{score:.2f}] {item.content}")
        return "\n".join(lines)
