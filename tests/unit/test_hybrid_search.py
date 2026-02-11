from vecna.memory.pg_store import PgMemoryStore


class DummyCursor:
    def __init__(self):
        self.queries = []
        self.params = []

    def execute(self, query, params):
        self.queries.append(query)
        self.params.append(params)

    def fetchall(self):
        return []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyConnection:
    def __init__(self):
        self.cursor_obj = DummyCursor()
        self.closed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        return None

    def rollback(self):
        return None


def _mock_embedder(_texts):
    return [[0.0] * 1536]


def test_hybrid_search_uses_ctes_and_weights(monkeypatch):
    store = PgMemoryStore(connection_string="postgresql://test", embedder=_mock_embedder)
    dummy_conn = DummyConnection()
    monkeypatch.setattr(store, "_get_connection", lambda: dummy_conn)

    store.search("hello world", top_k=5, hybrid=True, vector_weight=0.7, text_weight=0.3)

    assert dummy_conn.cursor_obj.queries
    query = dummy_conn.cursor_obj.queries[0]

    assert "WITH vector_scores AS" in query
    assert "text_scores AS" in query
    assert "COALESCE(v.vec_score, 0)" in query
    assert "COALESCE(t.text_score, 0)" in query

    params = dummy_conn.cursor_obj.params[0]
    assert params[-1] == 5
    assert params[2] == 0.0


def test_hybrid_search_falls_back_without_text_tokens(monkeypatch):
    store = PgMemoryStore(connection_string="postgresql://test", embedder=_mock_embedder)
    dummy_conn = DummyConnection()
    monkeypatch.setattr(store, "_get_connection", lambda: dummy_conn)

    store.search("!!!", top_k=3, hybrid=True)

    assert dummy_conn.cursor_obj.queries
    query = dummy_conn.cursor_obj.queries[0]
    assert "WITH vector_scores" not in query

    params = dummy_conn.cursor_obj.params[0]
    assert params[-1] == 3


def test_hybrid_search_keeps_filter_params_before_second_vector(monkeypatch):
    store = PgMemoryStore(connection_string="postgresql://test", embedder=_mock_embedder)
    dummy_conn = DummyConnection()
    monkeypatch.setattr(store, "_get_connection", lambda: dummy_conn)

    store.search("hello world", top_k=5, hybrid=True, domain="ai")

    params = dummy_conn.cursor_obj.params[0]
    assert params[1] == "ai"
    assert params[2].startswith("[0.0")
