class ToolRegistry:
    def __init__(self, register_defaults: bool = True) -> None:
        self.tools = {}
        if register_defaults:
            self.register_defaults()

    def register(self, name: str, func, description: str) -> None:
        self.tools[name] = {
            "func": func,
            "description": description,
        }

    def register_defaults(self) -> None:
        from vecna.tools.memory_tools import memory_get, memory_search

        self.register(
            "memory_search",
            memory_search,
            "Search semantic memory for relevant items by query.",
        )
        self.register(
            "memory_get",
            memory_get,
            "Fetch a specific memory item by id.",
        )
