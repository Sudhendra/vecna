from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import hashlib

from vecna.config.schema import VecnaConfig
from vecna.core.types import Belief, Fact
from vecna.memory.pg_store import MemoryItem, PgMemoryStore


@dataclass
class MarkdownChunk:
    content: str
    source_file: str
    line_start: int
    line_end: int
    heading_path: str
    content_hash: str


@dataclass
class MemoryMirror:
    workspace_dir: Path
    pg_store: Optional[PgMemoryStore]
    config: VecnaConfig

    async def index_markdown_files(self) -> int:
        if self.pg_store is None:
            return 0
        changed_files = await self.get_changed_files()
        indexed = 0
        for path in changed_files:
            rel_path = str(path.relative_to(self.workspace_dir))
            content = path.read_text(encoding="utf-8")
            chunks = self.chunk_markdown(content, rel_path)
            file_hash = self._hash_content(content)
            indexed += self.pg_store.upsert_markdown_chunks(rel_path, file_hash, chunks)
        stored_hashes = self.pg_store.get_markdown_file_hashes()
        for path, _hash in stored_hashes.items():
            full_path = self.workspace_dir / path
            if not full_path.exists():
                self.pg_store.delete_markdown_file(path)
        return indexed

    async def extract_facts_to_pg(self, facts: List[Fact], beliefs: List[Belief]) -> None:
        if self.pg_store is None:
            return
        items: List[MemoryItem] = []
        for fact in facts:
            items.append(
                MemoryItem(
                    content=fact.content,
                    item_type="fact",
                    confidence=fact.confidence,
                    domain=fact.domain,
                    source_model=fact.source_model or None,
                    metadata={
                        "fact_id": fact.id,
                        "evidence": fact.evidence,
                        "timestamp": fact.timestamp.isoformat(),
                    },
                )
            )
        for belief in beliefs:
            items.append(
                MemoryItem(
                    content=belief.content,
                    item_type="belief",
                    confidence=belief.confidence,
                    domain="general",
                    source_model=belief.source_model or None,
                    metadata={
                        "belief_id": belief.id,
                        "reasoning": belief.reasoning,
                        "supporting_facts": belief.supporting_facts,
                        "timestamp": belief.timestamp.isoformat(),
                    },
                )
            )
        if items:
            self.pg_store.add_items_batch(items)

    async def promote_to_memory(
        self,
        facts: List[Fact],
        beliefs: List[Belief],
        key_decisions: Optional[List[str]] = None,
        open_questions: Optional[List[str]] = None,
    ) -> None:
        memory_path = self.workspace_dir / "MEMORY.md"
        if not memory_path.exists():
            memory_path.write_text("# MEMORY\n\n", encoding="utf-8")

        lines: List[str] = []
        if key_decisions:
            lines.append("## Key Decisions")
            lines.extend([f"- {decision}" for decision in key_decisions])
            lines.append("")
        if facts:
            lines.append("## Learned Facts")
            lines.extend([f"- {fact.content}" for fact in facts])
            lines.append("")
        if beliefs:
            lines.append("## Patterns & Preferences")
            lines.extend([f"- {belief.content}" for belief in beliefs])
            lines.append("")
        if open_questions:
            lines.append("## Open Questions")
            lines.extend([f"- {question}" for question in open_questions])
            lines.append("")

        if not lines:
            return

        with memory_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines))

    async def update_working(self, task_state: str, next_steps: str, blockers: str) -> None:
        working_path = self.workspace_dir / "WORKING.md"
        content = (
            "# WORKING\n\n"
            f"## Current Task\n{task_state}\n\n"
            f"## Next Steps\n{next_steps}\n\n"
            f"## Blockers\n{blockers}\n"
        )
        working_path.write_text(content, encoding="utf-8")

    async def append_daily_log(self, summary: str, timestamp: datetime) -> None:
        memory_dir = self.workspace_dir / "memory"
        memory_dir.mkdir(exist_ok=True)
        log_path = memory_dir / f"{timestamp.date().isoformat()}.md"
        entry = f"## {timestamp.strftime('%H:%M')} UTC — Session Summary\n\n{summary}\n\n"
        if not log_path.exists():
            log_path.write_text(f"# {timestamp.date().isoformat()}\n\n", encoding="utf-8")
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(entry)

    def chunk_markdown(self, content: str, source_file: str) -> List[MarkdownChunk]:
        lines = content.splitlines()
        if not lines:
            return []

        chunks: List[MarkdownChunk] = []
        current_heading: List[str] = []
        start_idx = 1
        buffer: List[str] = []
        token_target = getattr(self.config.memory, "markdown_chunk_tokens", 400)

        def estimate_tokens(text: str) -> int:
            return max(1, len(text.split()))

        def flush(end_idx: int) -> None:
            if not buffer:
                return
            text = "\n".join(buffer).strip()
            if not text:
                return
            heading_path = " > ".join(current_heading) if current_heading else "Root"
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            chunks.append(
                MarkdownChunk(
                    content=text,
                    source_file=source_file,
                    line_start=start_idx,
                    line_end=end_idx,
                    heading_path=heading_path,
                    content_hash=content_hash,
                )
            )

        def split_large_buffer() -> None:
            nonlocal buffer, start_idx
            if estimate_tokens("\n".join(buffer)) <= token_target:
                return
            paragraphs: List[str] = []
            current: List[str] = []
            for line in buffer:
                if not line.strip() and current:
                    paragraphs.append("\n".join(current))
                    current = []
                else:
                    current.append(line)
            if current:
                paragraphs.append("\n".join(current))
            buffer = []
            line_cursor = start_idx
            for para in paragraphs:
                para_lines = para.splitlines()
                para_end = line_cursor + len(para_lines) - 1
                buffer.append(para)
                if estimate_tokens("\n".join(buffer)) >= token_target:
                    flush(para_end)
                    buffer = []
                    start_idx = para_end + 1
                line_cursor = para_end + 1
            if not buffer:
                start_idx = line_cursor

        for idx, line in enumerate(lines, start=1):
            if line.startswith("## "):
                split_large_buffer()
                flush(idx - 1)
                current_heading = [line[3:].strip()]
                start_idx = idx
                buffer = [line]
                continue
            if line.startswith("### "):
                split_large_buffer()
                flush(idx - 1)
                if current_heading:
                    current_heading = [current_heading[0], line[4:].strip()]
                else:
                    current_heading = [line[4:].strip()]
                start_idx = idx
                buffer = [line]
                continue
            buffer.append(line)

        split_large_buffer()
        flush(len(lines))
        return chunks

    async def get_changed_files(self) -> List[Path]:
        if self.pg_store is None:
            return []
        stored_hashes = self.pg_store.get_markdown_file_hashes()
        changed: List[Path] = []

        for path in self._iter_markdown_files():
            rel_path = str(path.relative_to(self.workspace_dir))
            content = path.read_text(encoding="utf-8")
            content_hash = self._hash_content(content)
            if stored_hashes.get(rel_path) != content_hash:
                changed.append(path)
        return changed

    def _hash_content(self, content: str) -> str:
        return hashlib.sha256(content.encode()).hexdigest()

    def _iter_markdown_files(self) -> List[Path]:
        files = []
        for name in ["SOUL.md", "MEMORY.md", "WORKING.md"]:
            path = self.workspace_dir / name
            if path.exists():
                files.append(path)
        memory_dir = self.workspace_dir / "memory"
        if memory_dir.exists():
            files.extend(memory_dir.glob("*.md"))
        return files
