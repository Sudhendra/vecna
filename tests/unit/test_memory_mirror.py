from datetime import datetime
from pathlib import Path

from vecna.config.schema import create_default_config
from vecna.memory.mirror import MemoryMirror


def test_chunk_markdown_preserves_headings():
    content = """
# Root

## Key Decisions

Decision content line one.

### Database Choice

We chose PostgreSQL for structured memory.

## Learned Facts

Fact content here.
"""
    mirror = MemoryMirror(workspace_dir=Path("/tmp"), pg_store=None, config=create_default_config())
    chunks = mirror.chunk_markdown(content, "MEMORY.md")

    assert chunks
    assert any(chunk.heading_path == "Key Decisions" for chunk in chunks)
    assert any(chunk.heading_path == "Key Decisions > Database Choice" for chunk in chunks)


def test_chunk_markdown_splits_large_sections():
    long_body = "word " * 500
    content = f"# Root\n\n## Section\n\n{long_body}"
    mirror = MemoryMirror(workspace_dir=Path("/tmp"), pg_store=None, config=create_default_config())
    chunks = mirror.chunk_markdown(content, "MEMORY.md")

    assert len(chunks) > 1
    assert "Section" in {chunk.heading_path for chunk in chunks}


def test_chunk_markdown_includes_line_ranges():
    content = """# Root

## Section One

Alpha

## Section Two

Beta
"""
    mirror = MemoryMirror(workspace_dir=Path("/tmp"), pg_store=None, config=create_default_config())
    chunks = mirror.chunk_markdown(content, "WORKING.md")

    assert all(chunk.line_start >= 1 for chunk in chunks)
    assert all(chunk.line_end >= chunk.line_start for chunk in chunks)


def test_chunk_markdown_hashes_content():
    content = """# Root

## Section

Content here.
"""
    mirror = MemoryMirror(workspace_dir=Path("/tmp"), pg_store=None, config=create_default_config())
    chunks = mirror.chunk_markdown(content, "WORKING.md")

    assert all(chunk.content_hash for chunk in chunks)
    assert len({chunk.content_hash for chunk in chunks}) == len(chunks)


async def test_get_changed_files_detects_updates(tmp_path):
    store = FakeStore({"MEMORY.md": "old"})
    mirror = MemoryMirror(
        workspace_dir=tmp_path,
        pg_store=store,  # type: ignore[arg-type]
        config=create_default_config(),
    )
    file_path = tmp_path / "MEMORY.md"
    file_path.write_text("content", encoding="utf-8")

    changed = await mirror.get_changed_files()
    assert tmp_path / "MEMORY.md" in changed


async def test_index_markdown_files_deletes_removed_files(tmp_path):
    store = FakeStore({"MEMORY.md": "old", "memory/2026-02-09.md": "old"})
    mirror = MemoryMirror(
        workspace_dir=tmp_path,
        pg_store=store,  # type: ignore[arg-type]
        config=create_default_config(),
    )
    (tmp_path / "MEMORY.md").write_text("content", encoding="utf-8")

    await mirror.index_markdown_files()

    assert "memory/2026-02-09.md" in store.deleted


async def test_append_daily_log_formats_timestamp(tmp_path):
    mirror = MemoryMirror(workspace_dir=tmp_path, pg_store=None, config=create_default_config())
    timestamp = datetime(2026, 2, 9, 14, 32)
    await mirror.append_daily_log("Summary", timestamp)

    daily_path = tmp_path / "memory" / "2026-02-09.md"
    text = daily_path.read_text(encoding="utf-8")
    assert "## 14:32 UTC" in text
    assert "Summary" in text


async def test_promote_to_memory_writes_decisions_and_questions(tmp_path):
    mirror = MemoryMirror(workspace_dir=tmp_path, pg_store=None, config=create_default_config())

    await mirror.promote_to_memory(
        facts=[],
        beliefs=[],
        key_decisions=["Use generated tsvector"],
        open_questions=["How should we archive old logs?"],
    )

    text = (tmp_path / "MEMORY.md").read_text(encoding="utf-8")
    assert "## Key Decisions" in text
    assert "Use generated tsvector" in text
    assert "## Open Questions" in text
    assert "How should we archive old logs?" in text


class FakeStore:
    def __init__(self, hashes):
        self.hashes = hashes
        self.deleted = []
        self.upserts = []

    def get_markdown_file_hashes(self):
        return self.hashes

    def delete_markdown_file(self, file_path: str) -> None:
        self.deleted.append(file_path)

    def upsert_markdown_chunks(self, source_file: str, file_hash: str, chunks):
        self.upserts.append((source_file, file_hash, chunks))
        return len(chunks)
