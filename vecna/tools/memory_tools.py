from vecna.memory.pg_store import PgMemoryStore


MEMORY_TOOL_ERRORS = (ImportError, OSError, RuntimeError, TypeError, ValueError)


def memory_search(query: str, max_results: int = 6, min_score: float = 0.35):
    try:
        store = PgMemoryStore()
        items = store.search(query, top_k=max_results)
    except MEMORY_TOOL_ERRORS:
        return []
    return [
        {
            "id": item.id,
            "content": item.content,
            "score": score,
            "item_type": item.item_type,
        }
        for item, score in items
        if score >= min_score
    ]


def memory_get(item_id: str):
    try:
        store = PgMemoryStore()
        item = store.get_item(item_id)
    except MEMORY_TOOL_ERRORS:
        return None
    if item is None:
        return None
    return {
        "id": item.id,
        "content": item.content,
        "item_type": item.item_type,
        "confidence": item.confidence,
        "domain": item.domain,
        "metadata": item.metadata,
    }
