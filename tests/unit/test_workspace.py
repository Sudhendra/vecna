from datetime import date
from pathlib import Path

from vecna.memory.workspace import init_workspace


def test_init_workspace_creates_default_files(tmp_path):
    paths = init_workspace(tmp_path)

    assert paths.workspace_dir == tmp_path
    assert paths.soul_path == tmp_path / "SOUL.md"
    assert paths.memory_path == tmp_path / "MEMORY.md"
    assert paths.working_path == tmp_path / "WORKING.md"
    assert paths.memory_dir == tmp_path / "memory"

    assert paths.soul_path.exists()
    assert paths.memory_path.exists()
    assert paths.working_path.exists()
    assert paths.memory_dir.is_dir()

    daily_log = tmp_path / "memory" / f"{date.today().isoformat()}.md"
    assert daily_log.exists()

    soul_content = paths.soul_path.read_text(encoding="utf-8")
    assert "I am Vecna" in soul_content


def test_init_workspace_does_not_overwrite_existing_files(tmp_path):
    soul_path = tmp_path / "SOUL.md"
    soul_path.write_text("custom soul", encoding="utf-8")

    init_workspace(tmp_path)

    assert soul_path.read_text(encoding="utf-8") == "custom soul"
