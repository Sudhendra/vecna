"""Memory consolidation helpers for grouping and merging similar memory items."""

from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Set
import re

from vecna.memory.pg_store import MemoryItem


@dataclass
class MemoryConsolidator:
    """Group similar memories and produce compact consolidated summaries."""

    similarity_threshold: float = 0.4

    def merge_candidates(self, items: List[MemoryItem]) -> List[List[MemoryItem]]:
        """Greedily merge candidate memories into similarity groups."""
        if not items:
            return []

        groups: List[List[MemoryItem]] = []
        token_cache = [self._tokens(item.content) for item in items]

        for index, item in enumerate(items):
            placed = False
            for group in groups:
                if self._belongs_in_group(item, token_cache[index], group):
                    group.append(item)
                    placed = True
                    break
            if not placed:
                groups.append([item])

        return groups

    def group_candidates(self, items: List[MemoryItem]) -> List[List[MemoryItem]]:
        """Backward-compatible alias for merge_candidates."""
        return self.merge_candidates(items)

    def consolidate_group(self, group: List[MemoryItem]) -> MemoryItem:
        """Merge a group of items into one deterministic summary item."""
        if not group:
            return MemoryItem(content="", metadata={"source_ids": []})

        sorted_group = sorted(group, key=lambda item: (item.id or "", item.content))
        source_contents = [
            item.content.strip() for item in sorted_group if item.content and item.content.strip()
        ]
        source_ids = [item.id for item in sorted_group if item.id]

        summary = "Consolidated memory: " + " | ".join(source_contents)
        confidence = sum(item.confidence for item in sorted_group) / len(sorted_group)
        item_type = self._most_common([item.item_type for item in sorted_group], default="fact")
        domain = self._most_common([item.domain for item in sorted_group], default="general")

        metadata: Dict[str, object] = {
            "source_ids": source_ids,
            "source_count": len(sorted_group),
        }

        return MemoryItem(
            content=summary,
            item_type=item_type,
            confidence=round(confidence, 4),
            domain=domain,
            metadata=metadata,
        )

    def _belongs_in_group(
        self, candidate: MemoryItem, candidate_tokens: Set[str], group: List[MemoryItem]
    ) -> bool:
        if not group:
            return False

        if candidate.domain and group[0].domain and candidate.domain != group[0].domain:
            return False

        similarities = []
        for group_item in group:
            group_tokens = self._tokens(group_item.content)
            similarities.append(self._jaccard(candidate_tokens, group_tokens))

        best_similarity = max(similarities) if similarities else 0.0
        return best_similarity >= self.similarity_threshold

    def _tokens(self, text: str) -> Set[str]:
        if not text:
            return set()
        return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if len(token) > 2}

    def _jaccard(self, left: Set[str], right: Set[str]) -> float:
        if not left or not right:
            return 0.0
        overlap_base = min(len(left), len(right))
        if overlap_base == 0:
            return 0.0
        return len(left & right) / overlap_base

    def _most_common(self, values: List[str], default: str) -> str:
        cleaned = [value for value in values if value]
        if not cleaned:
            return default
        counts = Counter(cleaned)
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return ranked[0][0]
