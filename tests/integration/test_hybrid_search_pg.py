import uuid

import pytest

from vecna.memory.pg_store import MemoryItem, PgMemoryStore


@pytest.mark.integration
def test_hybrid_search_combines_scores(pg_memory_store: PgMemoryStore):
    batch_id = str(uuid.uuid4())[:8]
    items = [
        MemoryItem(
            content=f"Hybrid keyword only {batch_id}",
            item_type="fact",
            confidence=0.8,
            domain="test",
            source_model="test",
        ),
        MemoryItem(
            content=f"Completely unrelated {batch_id}",
            item_type="fact",
            confidence=0.8,
            domain="test",
            source_model="test",
        ),
    ]
    pg_memory_store.add_items_batch(items)

    results = pg_memory_store.search(
        f"Hybrid keyword only {batch_id}",
        top_k=5,
        hybrid=True,
    )

    assert results
    assert any(batch_id in item.content for item, _score in results)
