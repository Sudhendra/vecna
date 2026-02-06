from vecna.tools.memory_tools import memory_search
from vecna.tools.registry import get_default_registry


def test_memory_search_returns_results(tmp_path):
    results = memory_search("api decision", max_results=3)
    assert isinstance(results, list)


def test_registry_registers_memory_tools_by_default():
    registry = get_default_registry()
    tools = {tool.name for tool in registry.list_tools()}

    assert "memory_search" in tools
    assert "memory_get" in tools
