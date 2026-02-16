from vecna.tools.registry import ToolRegistry, get_default_registry
from vecna.tools.types import ToolResult, ToolSpec


def test_registry_register_and_get():
    registry = ToolRegistry()
    spec = ToolSpec(name="python_exec", description="Run python", input_schema={"code": "string"})
    registry.register(spec, executor=lambda args, ctx: ToolResult("python_exec", True, ""))
    assert registry.get("python_exec").spec.name == "python_exec"


def test_registry_list_tools():
    registry = ToolRegistry()
    spec = ToolSpec(name="python_exec", description="Run python", input_schema={"code": "string"})
    registry.register(spec, executor=lambda args, ctx: ToolResult("python_exec", True, ""))
    assert "python_exec" in [t.name for t in registry.list_tools()]


def test_default_registry_includes_new_tools():
    registry = get_default_registry()
    specs_by_name = {spec.name: spec for spec in registry.list_tools()}

    assert "http_request" in specs_by_name
    assert "web_search" in specs_by_name
    assert "fs_read" in specs_by_name
    assert "fs_list" in specs_by_name

    assert specs_by_name["http_request"].tags == ["web", "http", "fetch"]
    assert specs_by_name["web_search"].tags == ["web", "search"]
    assert specs_by_name["fs_read"].tags == ["filesystem", "read"]
    assert specs_by_name["fs_list"].tags == ["filesystem", "list"]
