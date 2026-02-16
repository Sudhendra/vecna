from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Union

from vecna.tools.code_executor import execute_code_tool
from vecna.tools.fs_tools import fs_list_executor, fs_read_executor
from vecna.tools.http_tool import http_request_executor
from vecna.tools.memory_tools import memory_get, memory_search
from vecna.tools.web_search_tool import web_search_executor
from vecna.tools.types import ToolExecutionContext, ToolResult, ToolSpec

ToolExecutor = Callable[[dict, ToolExecutionContext], Union[ToolResult, Awaitable[ToolResult]]]


@dataclass
class RegisteredTool:
    spec: ToolSpec
    executor: ToolExecutor


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, RegisteredTool] = {}

    def register(self, spec: ToolSpec, executor: ToolExecutor) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool already registered: {spec.name}")
        self._tools[spec.name] = RegisteredTool(spec=spec, executor=executor)

    def get(self, name: str) -> RegisteredTool:
        return self._tools[name]

    def list_tools(self) -> List[ToolSpec]:
        return [rt.spec for rt in self._tools.values()]


def get_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="python_exec",
            description="Execute Python in the RLM sandbox",
            input_schema={"code": "string"},
        ),
        executor=execute_code_tool,
    )
    registry.register(
        ToolSpec(
            name="memory_search",
            description="Search semantic memory for relevant items by query.",
            input_schema={"query": "string", "max_results": "int", "min_score": "float"},
        ),
        executor=lambda args, ctx: ToolResult("memory_search", True, memory_search(**args)),
    )
    registry.register(
        ToolSpec(
            name="memory_get",
            description="Fetch a specific memory item by id.",
            input_schema={"item_id": "string"},
        ),
        executor=lambda args, ctx: ToolResult("memory_get", True, memory_get(**args)),
    )
    registry.register(
        ToolSpec(
            name="http_request",
            description="Fetch web content over HTTP/HTTPS with safety controls.",
            input_schema={"url": "string"},
            tags=["web", "http", "fetch"],
        ),
        executor=http_request_executor,
    )
    registry.register(
        ToolSpec(
            name="web_search",
            description="Search the web and return ranked results.",
            input_schema={"query": "string", "max_results": "int"},
            tags=["web", "search"],
        ),
        executor=web_search_executor,
    )
    registry.register(
        ToolSpec(
            name="fs_read",
            description="Read file contents from allowed filesystem roots.",
            input_schema={"path": "string"},
            tags=["filesystem", "read"],
        ),
        executor=fs_read_executor,
    )
    registry.register(
        ToolSpec(
            name="fs_list",
            description="List directory entries from allowed filesystem roots.",
            input_schema={"path": "string"},
            tags=["filesystem", "list"],
        ),
        executor=fs_list_executor,
    )
    return registry
