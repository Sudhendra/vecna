import re

from vecna.tools.types import ToolSpec


class ToolRouter:
    def __init__(self) -> None:
        self._stats = {}

    def record(self, tool_name: str, success: bool) -> None:
        stats = self._stats.setdefault(tool_name, {"success": 0, "total": 0})
        stats["total"] += 1
        if success:
            stats["success"] += 1

    def rank(self, tool_names: list[str]) -> list[str]:
        def score(name: str) -> float:
            return self.success_rate(name)

        indexed = list(enumerate(tool_names))
        indexed.sort(key=lambda item: (score(item[1]), -item[0]), reverse=True)
        return [name for _, name in indexed]

    def success_rate(self, tool_name: str) -> float:
        stats = self._stats.get(tool_name)
        if not stats or stats["total"] == 0:
            return 0.0
        return stats["success"] / stats["total"]

    def rank_specs_for_query(self, specs: list[ToolSpec], query: str) -> list[ToolSpec]:
        query_terms = self._tokenize(query)
        indexed_specs = list(enumerate(specs))

        def score(item: tuple[int, ToolSpec]) -> tuple[int, float, int]:
            index, spec = item
            overlap = len(query_terms & self._spec_terms(spec))
            return overlap, self.success_rate(spec.name), -index

        indexed_specs.sort(key=score, reverse=True)
        return [spec for _, spec in indexed_specs]

    def _spec_terms(self, spec: ToolSpec) -> set[str]:
        name_terms = set(spec.name.lower().split("_"))
        description_terms = self._tokenize(spec.description)
        tag_terms = {tag.lower() for tag in spec.tags}
        return name_terms | description_terms | tag_terms

    def _tokenize(self, text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9_]+", text.lower()))
