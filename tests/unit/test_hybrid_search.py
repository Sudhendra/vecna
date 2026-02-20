from vecna.memory.pg_store import PgMemoryStore


class DummyCursor:
    def __init__(self, rows=None):
        self.queries = []
        self.params = []
        self.rows = rows or []

    def execute(self, query, params):
        self.queries.append(query)
        self.params.append(params)

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class DummyConnection:
    def __init__(self, rows=None):
        self.cursor_obj = DummyCursor(rows=rows)
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

    assert "WITH vector_candidates AS" in query
    assert "text_candidates AS" in query
    assert "candidate_ids AS" in query
    assert "UNION" in query
    assert "JOIN candidate_ids c ON m.id = c.id" in query
    assert "v.vec_score" in query

    params = dummy_conn.cursor_obj.params[0]
    assert params[4] == 25
    assert params[-1] == 25
    assert params[5] == "hello world"
    assert params[6] == "hello world"
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
    assert params[6] == "ai"
    assert params[2].startswith("[0.0")
    assert params[4].startswith("[0.0")
    assert params[-1] == 25


def test_tokenize_normalizes_text():
    store = PgMemoryStore(connection_string="postgresql://test", embedder=_mock_embedder)

    assert store.tokenize_text("Neural-cache consistency, v2.0!") == [
        "neural",
        "cache",
        "consistency",
        "v2",
        "0",
    ]


def test_bm25_score_rewards_exact_term_coverage():
    store = PgMemoryStore(connection_string="postgresql://test", embedder=_mock_embedder)

    query_tokens = ["neural", "cache", "consistency"]
    corpus_tokens = [
        ["neural", "cache", "consistency", "check"],
        ["cache", "check", "status", "note"],
    ]

    exact_score = store.score_bm25(query_tokens, corpus_tokens[0], corpus_tokens)
    loose_score = store.score_bm25(query_tokens, corpus_tokens[1], corpus_tokens)

    assert exact_score > loose_score


def test_hybrid_search_combines_vector_and_bm25(monkeypatch):
    store = PgMemoryStore(connection_string="postgresql://test", embedder=_mock_embedder)

    rows = [
        (
            "11111111-1111-1111-1111-111111111111",
            "exact term match",
            "fact",
            0.9,
            "test",
            "test",
            [0.0] * 1536,
            {},
            0,
            None,
            None,
            None,
            0.4,
        ),
        (
            "22222222-2222-2222-2222-222222222222",
            "loose related text",
            "fact",
            0.9,
            "test",
            "test",
            [0.0] * 1536,
            {},
            0,
            None,
            None,
            None,
            0.9,
        ),
    ]

    dummy_conn = DummyConnection(rows=rows)
    monkeypatch.setattr(store, "_get_connection", lambda: dummy_conn)
    monkeypatch.setattr(store, "_update_retrieval_stats", lambda _item_ids: None)

    bm25_scores = {
        "exact term match": 1.0,
        "loose related text": 0.0,
    }

    def _fake_bm25(_query_tokens, doc_tokens, _corpus_tokens):
        content = " ".join(doc_tokens)
        return bm25_scores.get(content, 0.0)

    monkeypatch.setattr(store, "_bm25_score", _fake_bm25)

    results = store.search(
        "exact term",
        top_k=2,
        hybrid=True,
        vector_weight=0.3,
        text_weight=0.7,
    )

    assert [item.content for item, _ in results] == ["exact term match", "loose related text"]
    assert results[0][1] == 0.82
    assert results[1][1] == 0.27


def test_vector_only_mode_does_not_use_bm25(monkeypatch):
    store = PgMemoryStore(connection_string="postgresql://test", embedder=_mock_embedder)
    dummy_conn = DummyConnection()
    monkeypatch.setattr(store, "_get_connection", lambda: dummy_conn)

    def _raise_if_called(*_args, **_kwargs):
        raise AssertionError("_bm25_score should not be called in vector-only mode")

    monkeypatch.setattr(store, "_bm25_score", _raise_if_called)

    store.search("vector only query", top_k=3, hybrid=False)
