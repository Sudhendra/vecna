"""Session-level pattern detection utilities for memory consolidation."""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class SessionPatternDetector:
    """Detect recurring themes in event/session records with frequency heuristics."""

    min_count: int = 2
    max_patterns: int = 5
    exclude_event_types: Optional[Set[str]] = field(default_factory=set)

    def detect(self, records: List[Any]) -> Dict[str, Any]:
        """Return deterministic recurring themes from input records."""
        if not records:
            return {"record_count": 0, "patterns": []}

        excluded = {event_type.strip().lower() for event_type in self.exclude_event_types or set()}
        filtered_records = [
            record for record in records if self._get_event_type(record) not in excluded
        ]

        if not filtered_records:
            return {"record_count": 0, "patterns": []}

        counts: Counter = Counter()
        for record in filtered_records:
            for theme in self._extract_themes(record):
                counts[theme] += 1

        patterns: List[Dict[str, Any]] = []
        total = len(filtered_records)
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))

        for theme, count in ranked:
            if count < self.min_count:
                continue
            patterns.append(
                {
                    "theme": theme,
                    "count": count,
                    "frequency": round(count / total, 4),
                }
            )
            if len(patterns) >= self.max_patterns:
                break

        return {"record_count": total, "patterns": patterns}

    def _extract_themes(self, record: Any) -> List[str]:
        """Extract normalized candidate themes from a record."""
        event_type = self._get_event_type(record)
        if isinstance(record, dict):
            payload = record.get("payload") or {}
        else:
            payload = getattr(record, "payload", {}) or {}

        themes = set()
        if isinstance(payload, dict):
            for key in ["topic", "domain", "theme"]:
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    themes.add(value.strip().lower())

            tags = payload.get("tags")
            if isinstance(tags, list):
                for tag in tags:
                    if isinstance(tag, str) and tag.strip():
                        themes.add(tag.strip().lower())

        if not themes and event_type and isinstance(event_type, str):
            themes.add(event_type)

        return sorted(themes)

    def _get_event_type(self, record: Any) -> str:
        """Extract and normalize event_type from dict-like or object records."""
        if isinstance(record, dict):
            event_type = record.get("event_type")
        else:
            event_type = getattr(record, "event_type", None)

        if isinstance(event_type, str):
            return event_type.strip().lower()
        return ""
