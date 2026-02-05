from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, List, Union

from vecna.tools.code_executor import execute_code_tool
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
    return registry
