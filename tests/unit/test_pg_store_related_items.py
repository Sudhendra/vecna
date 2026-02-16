"""Unit tests for PgMemoryStore related-items SQL traversal."""

from typing import Any, List, Optional, Tuple

from vecna.memory.pg_store import PgMemoryStore


class _FakeCursor:
    def __init__(self, rows: Optional[List[Tuple[Any, ...]]] = None):
        self.rows = rows or []
        self.executed_query: Optional[str] = None
        self.executed_params: Optional[List[Any]] = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def execute(self, query: str, params: List[Any]):
        self.executed_query = query
        self.executed_params = params

    def fetchall(self) -> List[Tuple[Any, ...]]:
        return self.rows


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor


def test_get_related_items_uses_recursive_cte(monkeypatch):
    store = PgMemoryStore(connection_string="postgresql://test:test@localhost:5432/test")
    cursor = _FakeCursor()
    conn = _FakeConnection(cursor)
    monkeypatch.setattr(store, "_get_connection", lambda: conn)

    store.get_related_items("00000000-0000-0000-0000-000000000001", max_depth=3)

    assert cursor.executed_query is not None
    assert "WITH RECURSIVE" in cursor.executed_query
    assert "t.depth < %(max_depth)s" in cursor.executed_query
    assert cursor.executed_params is not None
    assert cursor.executed_params["max_depth"] == 3
