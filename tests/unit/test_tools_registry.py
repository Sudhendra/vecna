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


def test_default_registry_can_disable_web_and_fs_tools():
    registry = get_default_registry(enable_web_tools=False, enable_fs_tools=False)
    names = {spec.name for spec in registry.list_tools()}

    assert "python_exec" in names
    assert "memory_search" in names
    assert "memory_get" in names
    assert "http_request" not in names
    assert "web_search" not in names
    assert "fs_read" not in names
    assert "fs_list" not in names
