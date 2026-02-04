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
            stats = self._stats.get(name)
            if not stats or stats["total"] == 0:
                return 0.0
            return stats["success"] / stats["total"]

        indexed = list(enumerate(tool_names))
        indexed.sort(key=lambda item: (score(item[1]), -item[0]), reverse=True)
        return [name for _, name in indexed]
