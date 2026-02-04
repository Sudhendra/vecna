from dataclasses import dataclass
from pathlib import Path

from vecna.memory.pg_store import MemoryItem


@dataclass
class MemoryMirror:
    base_dir: Path

    def scan_daily(self):
        items = []
        memory_dir = self.base_dir / "memory"
        for path in memory_dir.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            if text.strip():
                items.append(MemoryItem(content=text, item_type="memory_log", domain="self"))
        return items
