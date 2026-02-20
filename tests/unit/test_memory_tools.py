from types import SimpleNamespace

from vecna.tools.memory_tools import memory_search
from vecna.tools.registry import get_default_registry


def test_memory_search_returns_results(monkeypatch):
    class FakeStore:
        def search(self, query, top_k):
            assert query == "api decision"
            assert top_k == 3
            return [
                (SimpleNamespace(id="id-1", content="API decision log", item_type="fact"), 0.88),
                (SimpleNamespace(id="id-2", content="Low score item", item_type="fact"), 0.10),
            ]

    monkeypatch.setattr("vecna.tools.memory_tools.PgMemoryStore", FakeStore)
    results = memory_search("api decision", max_results=3)
    assert results == [
        {
            "id": "id-1",
            "content": "API decision log",
            "score": 0.88,
            "item_type": "fact",
        }
    ]


def test_registry_registers_memory_tools_by_default():
    registry = get_default_registry()
    tools = {tool.name for tool in registry.list_tools()}

    assert "memory_search" in tools
    assert "memory_get" in tools
