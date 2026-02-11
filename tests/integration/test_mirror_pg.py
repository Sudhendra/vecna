from datetime import datetime
import asyncio

import pytest

from vecna.config.schema import create_default_config
from vecna.memory.mirror import MemoryMirror


@pytest.mark.integration
def test_mirror_indexes_markdown_to_pg(tmp_path, pg_memory_store):
    config = create_default_config()
    mirror = MemoryMirror(workspace_dir=tmp_path, pg_store=pg_memory_store, config=config)

    memory_dir = tmp_path / "memory"
    memory_dir.mkdir()
    (tmp_path / "MEMORY.md").write_text("# MEMORY\n\n## Learned Facts\n- Alpha", encoding="utf-8")

    indexed = asyncio.run(mirror.index_markdown_files())

    assert indexed >= 1
    hashes = pg_memory_store.get_markdown_file_hashes()
    assert "MEMORY.md" in hashes


@pytest.mark.integration
def test_append_daily_log_creates_file(tmp_path, pg_memory_store):
    config = create_default_config()
    mirror = MemoryMirror(workspace_dir=tmp_path, pg_store=pg_memory_store, config=config)

    asyncio.run(mirror.append_daily_log("Summary", datetime(2026, 2, 9, 14, 32)))

    path = tmp_path / "memory" / "2026-02-09.md"
    assert path.exists()
