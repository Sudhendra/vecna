from vecna.memory.mirror import MemoryMirror


def test_mirror_parses_daily_log(tmp_path):
    daily = tmp_path / "memory" / "2026-02-03.md"
    daily.parent.mkdir()
    daily.write_text("# 2026-02-03\n\n## 10:00 AM - Note\nLearned X")
    mirror = MemoryMirror(base_dir=tmp_path)
    items = mirror.scan_daily()
    assert items and items[0].item_type == "memory_log"
