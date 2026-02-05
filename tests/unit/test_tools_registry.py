from vecna.tools.registry import ToolRegistry
from vecna.tools.types import ToolSpec


def test_registry_register_and_get():
    registry = ToolRegistry()
    spec = ToolSpec(name="python_exec", description="Run python", input_schema={"code": "string"})
    registry.register(spec, executor=lambda args, ctx: None)
    assert registry.get("python_exec").spec.name == "python_exec"


def test_registry_list_tools():
    registry = ToolRegistry()
    spec = ToolSpec(name="python_exec", description="Run python", input_schema={"code": "string"})
    registry.register(spec, executor=lambda args, ctx: None)
    assert "python_exec" in [t.name for t in registry.list_tools()]
