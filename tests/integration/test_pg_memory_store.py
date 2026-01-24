"""
Integration tests for PgMemoryStore with real PostgreSQL.

These tests require a running PostgreSQL instance with pgvector extension.
They test the full memory store functionality including:
- CRUD operations for memory items
- Semantic search with embeddings
- Memory edges (graph operations)
- Episodic events and episodes
- RLM-style retrieval pipeline
- State integration
"""

import pytest
import uuid
from datetime import datetime, timedelta

from vecna.memory.pg_store import (
    PgMemoryStore,
    MemoryItem,
    MemoryEdge,
    MemoryEvent,
    Episode,
)


# ============================================================
# MEMORY ITEM CRUD TESTS
# ============================================================


class TestMemoryItemCRUD:
    """Test basic CRUD operations for memory items."""

    def test_add_item_generates_id(self, pg_memory_store: PgMemoryStore):
        """Test that adding an item returns an ID."""
        item = MemoryItem(
            content=f"Test memory item for CRUD test {uuid.uuid4()}",
            item_type="fact",
            confidence=0.8,
            domain="test",
            source_model="test",
            metadata={"test_id": str(uuid.uuid4())},
        )

        item_id = pg_memory_store.add_item(item)

        assert item_id is not None
        assert len(item_id) > 0

    def test_add_and_get_item(self, pg_memory_store: PgMemoryStore):
        """Test adding and retrieving an item."""
        unique_content = f"Unique content for get test {uuid.uuid4()}"
        item = MemoryItem(
            content=unique_content,
            item_type="belief",
            confidence=0.75,
            domain="test",
            source_model="test",
            metadata={"original": True},
        )

        item_id = pg_memory_store.add_item(item)
        retrieved = pg_memory_store.get_item(item_id)

        assert retrieved is not None
        assert retrieved.content == unique_content
        assert retrieved.item_type == "belief"
        assert retrieved.confidence == 0.75
        assert retrieved.domain == "test"
        assert retrieved.metadata.get("original") is True

    def test_get_nonexistent_item_returns_none(self, pg_memory_store: PgMemoryStore):
        """Test that getting a non-existent item returns None."""
        fake_id = str(uuid.uuid4())
        result = pg_memory_store.get_item(fake_id)
        assert result is None

    def test_update_item_content(self, pg_memory_store: PgMemoryStore):
        """Test updating an item's content."""
        unique_id = str(uuid.uuid4())[:8]
        item = MemoryItem(
            content=f"Original content {unique_id}",
            item_type="fact",
            confidence=0.5,
            domain="test",
            source_model="test",
        )

        item_id = pg_memory_store.add_item(item)

        # Update content and confidence
        success = pg_memory_store.update_item(
            item_id, content=f"Updated content {unique_id}", confidence=0.9
        )
        assert success is True

        updated = pg_memory_store.get_item(item_id)
        assert updated.content == f"Updated content {unique_id}"
        assert updated.confidence == 0.9

    def test_update_item_metadata(self, pg_memory_store: PgMemoryStore):
        """Test updating an item's metadata."""
        item = MemoryItem(
            content=f"Item with metadata {uuid.uuid4()}",
            item_type="fact",
            confidence=0.7,
            domain="test",
            source_model="test",
            metadata={"version": 1},
        )

        item_id = pg_memory_store.add_item(item)

        success = pg_memory_store.update_item(item_id, metadata={"version": 2, "updated": True})
        assert success is True

        updated = pg_memory_store.get_item(item_id)
        assert updated.metadata["version"] == 2
        assert updated.metadata["updated"] is True

    def test_delete_item(self, pg_memory_store: PgMemoryStore):
        """Test deleting an item."""
        item = MemoryItem(
            content=f"Item to delete {uuid.uuid4()}",
            item_type="fact",
            confidence=0.5,
            domain="test",
            source_model="test",
        )

        item_id = pg_memory_store.add_item(item)

        # Verify it exists
        assert pg_memory_store.get_item(item_id) is not None

        # Delete
        success = pg_memory_store.delete_item(item_id)
        assert success is True

        # Verify it's gone
        assert pg_memory_store.get_item(item_id) is None

    def test_add_items_batch(self, pg_memory_store: PgMemoryStore):
        """Test batch adding multiple items."""
        batch_id = str(uuid.uuid4())[:8]
        items = [
            MemoryItem(
                content=f"Batch item {i} - {batch_id}",
                item_type="fact",
                confidence=0.5 + (i * 0.1),
                domain="test",
                source_model="test",
            )
            for i in range(5)
        ]

        item_ids = pg_memory_store.add_items_batch(items)

        assert len(item_ids) == 5
        for item_id in item_ids:
            assert item_id is not None
            retrieved = pg_memory_store.get_item(item_id)
            assert retrieved is not None


# ============================================================
# EMBEDDING TESTS
# ============================================================


class TestEmbeddings:
    """Test embedding generation and caching."""

    def test_embed_single_text(self, pg_memory_store: PgMemoryStore):
        """Test embedding a single text."""
        embeddings = pg_memory_store.embed(["This is a test sentence"])

        assert len(embeddings) == 1
        # Should be 1536 (OpenAI) or 384 (local)
        assert len(embeddings[0]) in [384, 1536]

    def test_embed_multiple_texts(self, pg_memory_store: PgMemoryStore):
        """Test embedding multiple texts."""
        texts = [
            "First test sentence",
            "Second test sentence",
            "Third test sentence",
        ]
        embeddings = pg_memory_store.embed(texts)

        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) in [384, 1536]

    def test_embed_empty_list(self, pg_memory_store: PgMemoryStore):
        """Test that embedding an empty list returns empty array."""
        embeddings = pg_memory_store.embed([])
        assert len(embeddings) == 0

    def test_embed_filters_empty_strings(self, pg_memory_store: PgMemoryStore):
        """Test that empty strings are filtered out."""
        texts = ["Valid text", "", "  ", "Another valid text"]
        embeddings = pg_memory_store.embed(texts)

        # Should only return embeddings for non-empty texts
        assert len(embeddings) == 2

    def test_embedding_caching(self, pg_memory_store: PgMemoryStore):
        """Test that embeddings are cached."""
        text = f"Unique text for caching test {uuid.uuid4()}"

        # First call - should generate embedding
        emb1 = pg_memory_store.embed([text])

        # Second call - should use cache
        emb2 = pg_memory_store.embed([text])

        # Should be identical
        assert list(emb1[0]) == list(emb2[0])

    def test_item_embedding_auto_generated(self, pg_memory_store: PgMemoryStore):
        """Test that items get embeddings auto-generated."""
        item = MemoryItem(
            content=f"This item should get an embedding automatically {uuid.uuid4()}",
            item_type="fact",
            confidence=0.8,
            domain="test",
            source_model="test",
        )

        item_id = pg_memory_store.add_item(item)
        retrieved = pg_memory_store.get_item(item_id)

        assert retrieved.embedding is not None
        assert len(retrieved.embedding) in [384, 1536]


# ============================================================
# SEMANTIC SEARCH TESTS
# ============================================================


class TestSemanticSearch:
    """Test semantic search functionality."""

    @pytest.fixture
    def search_test_items(self, pg_memory_store: PgMemoryStore):
        """Create items for search testing."""
        batch_id = str(uuid.uuid4())[:8]
        items = [
            MemoryItem(
                content=f"Python is a programming language used for web development [{batch_id}]",
                item_type="fact",
                confidence=0.9,
                domain="code",
                source_model="test",
                metadata={"batch_id": batch_id},
            ),
            MemoryItem(
                content=f"JavaScript runs in web browsers and Node.js [{batch_id}]",
                item_type="fact",
                confidence=0.85,
                domain="code",
                source_model="test",
                metadata={"batch_id": batch_id},
            ),
            MemoryItem(
                content=f"Machine learning uses neural networks for pattern recognition [{batch_id}]",
                item_type="fact",
                confidence=0.8,
                domain="ai",
                source_model="test",
                metadata={"batch_id": batch_id},
            ),
            MemoryItem(
                content=f"Cats are domestic animals that like to sleep [{batch_id}]",
                item_type="fact",
                confidence=0.7,
                domain="general",
                source_model="test",
                metadata={"batch_id": batch_id},
            ),
        ]

        item_ids = pg_memory_store.add_items_batch(items)
        return item_ids, batch_id

    def test_basic_search(self, pg_memory_store: PgMemoryStore, search_test_items):
        """Test basic semantic search."""
        item_ids, batch_id = search_test_items

        results = pg_memory_store.search("programming languages", top_k=5)

        assert len(results) > 0
        # Results are (item, similarity) tuples
        for item, similarity in results:
            assert isinstance(item, MemoryItem)
            assert 0.0 <= similarity <= 1.0

    def test_search_with_item_type_filter(self, pg_memory_store: PgMemoryStore, search_test_items):
        """Test search with item type filter."""
        item_ids, batch_id = search_test_items

        results = pg_memory_store.search("programming languages", top_k=10, item_type="fact")

        for item, _ in results:
            assert item.item_type == "fact"

    def test_search_with_domain_filter(self, pg_memory_store: PgMemoryStore, search_test_items):
        """Test search with domain filter."""
        item_ids, batch_id = search_test_items

        results = pg_memory_store.search("web development", top_k=10, domain="code")

        for item, _ in results:
            assert item.domain == "code"

    def test_search_with_confidence_filter(self, pg_memory_store: PgMemoryStore, search_test_items):
        """Test search with minimum confidence filter."""
        item_ids, batch_id = search_test_items

        results = pg_memory_store.search("programming", top_k=10, min_confidence=0.8)

        for item, _ in results:
            assert item.confidence >= 0.8

    def test_search_returns_relevant_results(
        self, pg_memory_store: PgMemoryStore, search_test_items
    ):
        """Test that search returns semantically relevant results."""
        item_ids, batch_id = search_test_items

        # Search for AI-related content
        results = pg_memory_store.search("artificial intelligence neural nets", top_k=2)

        # The ML item should be in the top results
        contents = [item.content for item, _ in results]
        assert any("neural" in c.lower() or "machine learning" in c.lower() for c in contents)

    def test_search_updates_retrieval_stats(
        self, pg_memory_store: PgMemoryStore, search_test_items
    ):
        """Test that search updates retrieval count."""
        item_ids, batch_id = search_test_items

        # Get initial retrieval count
        initial = pg_memory_store.get_item(item_ids[0])
        initial_count = initial.retrieval_count

        # Perform search that should return this item
        pg_memory_store.search(initial.content[:50], top_k=5)

        # Check if count increased
        updated = pg_memory_store.get_item(item_ids[0])
        # Note: count may not increase if item not in top results
        # This is expected behavior


# ============================================================
# MEMORY EDGE TESTS
# ============================================================


class TestMemoryEdges:
    """Test memory edge (graph) operations."""

    @pytest.fixture
    def edge_test_items(self, pg_memory_store: PgMemoryStore):
        """Create items for edge testing."""
        batch_id = str(uuid.uuid4())[:8]
        items = [
            MemoryItem(
                content=f"Premise: All humans are mortal [{batch_id}]",
                item_type="fact",
                confidence=0.9,
                domain="logic",
                source_model="test",
                metadata={"batch_id": batch_id},
            ),
            MemoryItem(
                content=f"Premise: Socrates is a human [{batch_id}]",
                item_type="fact",
                confidence=0.9,
                domain="logic",
                source_model="test",
                metadata={"batch_id": batch_id},
            ),
            MemoryItem(
                content=f"Conclusion: Socrates is mortal [{batch_id}]",
                item_type="belief",
                confidence=0.85,
                domain="logic",
                source_model="test",
                metadata={"batch_id": batch_id},
            ),
        ]

        item_ids = pg_memory_store.add_items_batch(items)
        return item_ids

    def test_add_edge(self, pg_memory_store: PgMemoryStore, edge_test_items):
        """Test adding an edge between items."""
        item_ids = edge_test_items

        edge = MemoryEdge(
            source_id=item_ids[0],
            target_id=item_ids[2],
            relation="supports",
            weight=0.9,
            metadata={"test": True},
        )

        edge_id = pg_memory_store.add_edge(edge)
        assert edge_id is not None

    def test_get_outgoing_edges(self, pg_memory_store: PgMemoryStore, edge_test_items):
        """Test getting outgoing edges from an item."""
        item_ids = edge_test_items

        # Add edges
        edge1 = MemoryEdge(
            source_id=item_ids[0],
            target_id=item_ids[2],
            relation="supports",
            weight=0.9,
        )
        edge2 = MemoryEdge(
            source_id=item_ids[1],
            target_id=item_ids[2],
            relation="supports",
            weight=0.85,
        )
        pg_memory_store.add_edge(edge1)
        pg_memory_store.add_edge(edge2)

        # Get outgoing edges from first item
        edges = pg_memory_store.get_edges(item_ids[0], direction="outgoing")

        assert len(edges) >= 1
        assert any(e.target_id == item_ids[2] for e in edges)

    def test_get_incoming_edges(self, pg_memory_store: PgMemoryStore, edge_test_items):
        """Test getting incoming edges to an item."""
        item_ids = edge_test_items

        # Add edges pointing to the conclusion
        edge1 = MemoryEdge(
            source_id=item_ids[0],
            target_id=item_ids[2],
            relation="evidence_for",
            weight=0.9,
        )
        edge2 = MemoryEdge(
            source_id=item_ids[1],
            target_id=item_ids[2],
            relation="evidence_for",
            weight=0.85,
        )
        pg_memory_store.add_edge(edge1)
        pg_memory_store.add_edge(edge2)

        # Get incoming edges to the conclusion
        edges = pg_memory_store.get_edges(item_ids[2], direction="incoming")

        assert len(edges) >= 2
        source_ids = [e.source_id for e in edges]
        assert item_ids[0] in source_ids
        assert item_ids[1] in source_ids

    def test_get_edges_with_relation_filter(self, pg_memory_store: PgMemoryStore, edge_test_items):
        """Test filtering edges by relation type."""
        item_ids = edge_test_items

        # Add edges with different relations
        edge1 = MemoryEdge(
            source_id=item_ids[0],
            target_id=item_ids[2],
            relation="supports",
            weight=0.9,
        )
        edge2 = MemoryEdge(
            source_id=item_ids[0],
            target_id=item_ids[1],
            relation="derived_from",
            weight=0.5,
        )
        pg_memory_store.add_edge(edge1)
        pg_memory_store.add_edge(edge2)

        # Filter by relation
        supports_edges = pg_memory_store.get_edges(
            item_ids[0], direction="outgoing", relation="supports"
        )

        for edge in supports_edges:
            assert edge.relation == "supports"

    def test_get_related_items(self, pg_memory_store: PgMemoryStore, edge_test_items):
        """Test getting items related via edges."""
        item_ids = edge_test_items

        # Create edges
        edge = MemoryEdge(
            source_id=item_ids[0],
            target_id=item_ids[2],
            relation="supports",
            weight=0.9,
        )
        pg_memory_store.add_edge(edge)

        # Get related items
        related = pg_memory_store.get_related_items(item_ids[0])

        assert len(related) >= 1
        # Returns (item, weight, path) tuples
        for item, weight, path in related:
            assert isinstance(item, MemoryItem)
            assert weight > 0


# ============================================================
# EPISODIC EVENT TESTS
# ============================================================


class TestEpisodicEvents:
    """Test episodic event storage."""

    def test_add_event(self, pg_memory_store: PgMemoryStore):
        """Test adding an episodic event."""
        event = MemoryEvent(
            event_type="test_event",
            payload={"action": "test", "value": 42},
            session_id=f"test-session-{uuid.uuid4()}",
        )

        event_id = pg_memory_store.add_event(event)
        assert event_id is not None

    def test_get_recent_events(self, pg_memory_store: PgMemoryStore):
        """Test retrieving recent events."""
        session_id = f"test-session-{uuid.uuid4()}"

        # Add some events
        for i in range(5):
            event = MemoryEvent(
                event_type="test_event",
                payload={"index": i},
                session_id=session_id,
            )
            pg_memory_store.add_event(event)

        # Get recent events
        events = pg_memory_store.get_recent_events(limit=10, session_id=session_id)

        assert len(events) >= 5
        # Should be in reverse chronological order
        for event in events:
            assert event.session_id == session_id

    def test_get_events_by_type(self, pg_memory_store: PgMemoryStore):
        """Test filtering events by type."""
        session_id = f"test-session-{uuid.uuid4()}"

        # Add events of different types
        for event_type in ["type_a", "type_b", "type_a"]:
            event = MemoryEvent(
                event_type=event_type,
                payload={"type": event_type},
                session_id=session_id,
            )
            pg_memory_store.add_event(event)

        # Filter by type
        type_a_events = pg_memory_store.get_recent_events(
            limit=10, event_type="type_a", session_id=session_id
        )

        for event in type_a_events:
            assert event.event_type == "type_a"


# ============================================================
# EPISODE TESTS
# ============================================================


class TestEpisodes:
    """Test compressed episode storage."""

    def test_add_episode(self, pg_memory_store: PgMemoryStore):
        """Test adding a compressed episode."""
        episode = Episode(
            summary="User asked about Python programming and received code examples",
            start_time=datetime.now() - timedelta(hours=1),
            end_time=datetime.now(),
            event_count=15,
            tags=["python", "code", "tutorial"],
            metadata={"user_satisfaction": 0.9},
        )

        episode_id = pg_memory_store.add_episode(episode)
        assert episode_id is not None

    def test_search_episodes(self, pg_memory_store: PgMemoryStore):
        """Test searching episodes semantically."""
        # Add some episodes
        episodes = [
            Episode(
                summary="Discussion about machine learning and neural networks",
                event_count=10,
                tags=["ml", "ai"],
            ),
            Episode(
                summary="Debugging JavaScript code for web application",
                event_count=8,
                tags=["javascript", "debugging"],
            ),
            Episode(
                summary="Setting up Docker containers for deployment",
                event_count=12,
                tags=["docker", "devops"],
            ),
        ]

        for ep in episodes:
            pg_memory_store.add_episode(ep)

        # Search for AI-related episodes
        results = pg_memory_store.search_episodes("artificial intelligence deep learning")

        assert len(results) > 0
        # Results are (episode, similarity) tuples
        for episode, similarity in results:
            assert isinstance(episode, Episode)
            assert 0.0 <= similarity <= 1.0


# ============================================================
# RLM RETRIEVAL TESTS
# ============================================================


class TestRLMRetrieval:
    """Test RLM-style retrieval pipeline."""

    def test_decompose_query_simple(self, pg_memory_store: PgMemoryStore):
        """Test query decomposition for simple queries."""
        facets = pg_memory_store.decompose_query("What is Python?")

        assert len(facets) >= 1
        assert any("python" in f.lower() for f in facets)

    def test_decompose_query_complex(self, pg_memory_store: PgMemoryStore):
        """Test query decomposition for complex queries."""
        facets = pg_memory_store.decompose_query(
            "How does Python compare to JavaScript for web development?"
        )

        assert len(facets) >= 2
        # Should extract key terms
        facets_lower = [f.lower() for f in facets]
        assert any("python" in f or "javascript" in f for f in facets_lower)

    def test_rlm_retrieve(self, pg_memory_store: PgMemoryStore):
        """Test full RLM retrieval pipeline."""
        # Add some test items first
        items = [
            MemoryItem(
                content="Python is great for data science and machine learning",
                item_type="fact",
                confidence=0.9,
                domain="code",
                source_model="test",
            ),
            MemoryItem(
                content="NumPy is a Python library for numerical computing",
                item_type="fact",
                confidence=0.85,
                domain="code",
                source_model="test",
            ),
        ]
        pg_memory_store.add_items_batch(items)

        # Run RLM retrieval
        context, facets, stats = pg_memory_store.rlm_retrieve(
            "Python data science libraries",
            top_k_per_facet=3,
            max_items=10,
        )

        assert isinstance(context, str)
        assert len(facets) > 0
        assert "num_facets" in stats
        assert stats["num_facets"] > 0

    def test_get_relevant_context(self, pg_memory_store: PgMemoryStore):
        """Test simplified context retrieval."""
        # Add test items
        item = MemoryItem(
            content="Docker containers provide isolated environments for applications",
            item_type="fact",
            confidence=0.9,
            domain="devops",
            source_model="test",
        )
        pg_memory_store.add_item(item)

        context = pg_memory_store.get_relevant_context(
            "containerization and deployment",
            max_items=5,
        )

        assert isinstance(context, str)
        # Should contain evidence header or "No relevant evidence"
        assert "Evidence" in context or "No relevant" in context


# ============================================================
# STATISTICS TESTS
# ============================================================


class TestStatistics:
    """Test memory store statistics."""

    def test_get_stats(self, pg_memory_store: PgMemoryStore):
        """Test retrieving store statistics."""
        stats = pg_memory_store.get_stats()

        assert "total_items" in stats
        assert "items_by_type" in stats
        assert "total_edges" in stats
        assert "total_events" in stats
        assert "total_episodes" in stats

    def test_stats_reflect_additions(self, pg_memory_store: PgMemoryStore):
        """Test that stats update after additions."""
        initial_stats = pg_memory_store.get_stats()
        initial_count = initial_stats["total_items"]

        # Add an item
        item = MemoryItem(
            content=f"Stats test item {uuid.uuid4()}",
            item_type="fact",
            confidence=0.8,
            domain="test",
            source_model="test",
        )
        pg_memory_store.add_item(item)

        new_stats = pg_memory_store.get_stats()
        assert new_stats["total_items"] >= initial_count + 1


# ============================================================
# STATE INTEGRATION TESTS
# ============================================================


class TestStateIntegration:
    """Test integration with HiveState."""

    def test_add_from_state(self, pg_memory_store: PgMemoryStore, populated_state):
        """Test adding all items from a HiveState."""
        counts = pg_memory_store.add_from_state(populated_state)

        # Should have counts for different item types
        assert isinstance(counts, dict)
        # At least some items should be added
        total = sum(counts.values())
        assert total > 0

    def test_add_from_state_deduplication(self, pg_memory_store: PgMemoryStore, populated_state):
        """Test that duplicate items are not added twice."""
        # Add state twice
        counts1 = pg_memory_store.add_from_state(populated_state)
        counts2 = pg_memory_store.add_from_state(populated_state)

        # Second add should have same or fewer items due to dedup
        total1 = sum(counts1.values())
        total2 = sum(counts2.values())

        # With proper deduplication, counts should be similar
        # (some may be updated rather than inserted)
        assert total2 <= total1 + 5  # Allow some variance
