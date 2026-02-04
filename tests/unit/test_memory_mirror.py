from pathlib import Path

from vecna.memory.mirror import MemoryMirror


def test_mirror_parses_daily_log(tmp_path):
    daily = tmp_path / "memory" / "2026-02-03.md"
    daily.parent.mkdir()
    daily.write_text("# 2026-02-03\n\n## 10:00 AM - Note\nLearned X")
    mirror = MemoryMirror(base_dir=tmp_path)
    items = mirror.scan_daily()
    assert items and items[0].item_type == "memory_log"
    assert items[0].domain == "self"


def test_scan_daily_missing_memory_dir_returns_empty(tmp_path, monkeypatch):
    mirror = MemoryMirror(base_dir=tmp_path)

    def fail_glob(_self, _pattern):
        raise AssertionError("glob should not be called")

    monkeypatch.setattr(Path, "glob", fail_glob)

    items = mirror.scan_daily()
    assert items == []
