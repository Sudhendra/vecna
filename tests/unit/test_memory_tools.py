from vecna.tools.memory_tools import memory_search


def test_memory_search_returns_results(tmp_path):
    results = memory_search("api decision", max_results=3)
    assert isinstance(results, list)
