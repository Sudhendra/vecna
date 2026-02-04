from vecna.tools.router import ToolRouter


class ToolAudit:
    def __init__(self, router: ToolRouter | None = None) -> None:
        self.router = router or ToolRouter()

    def record(self, tool_name: str, success: bool) -> None:
        self.router.record(tool_name, success)
