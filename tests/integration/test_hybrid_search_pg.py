import uuid

import pytest

from vecna.memory.pg_store import MemoryItem, PgMemoryStore


@pytest.mark.integration
def test_hybrid_search_combines_scores(pg_memory_store: PgMemoryStore):
    batch_id = str(uuid.uuid4())[:8]
    exact_phrase = f"neural cache consistency {batch_id}"
    items = [
        MemoryItem(
            content=exact_phrase,
            item_type="fact",
            confidence=0.8,
            domain="test",
            source_model="test",
        ),
        MemoryItem(
            content=f"neural cache notes around deployment for {batch_id}",
            item_type="fact",
            confidence=0.8,
            domain="test",
            source_model="test",
        ),
        MemoryItem(
            content=f"Completely unrelated entry {batch_id}",
            item_type="fact",
            confidence=0.8,
            domain="test",
            source_model="test",
        ),
    ]
    pg_memory_store.add_items_batch(items)

    results = pg_memory_store.search(
        exact_phrase,
        top_k=5,
        hybrid=True,
        vector_weight=0.2,
        text_weight=0.8,
    )

    assert results
    assert batch_id in results[0][0].content
    assert results[0][0].content == exact_phrase
