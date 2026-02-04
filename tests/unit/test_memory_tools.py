from vecna.tools.memory_tools import memory_search
from vecna.tools.registry import ToolRegistry


def test_memory_search_returns_results(tmp_path):
    results = memory_search("api decision", max_results=3)
    assert isinstance(results, list)


def test_registry_registers_memory_tools_by_default():
    registry = ToolRegistry()

    assert "memory_search" in registry.tools
    assert "memory_get" in registry.tools
