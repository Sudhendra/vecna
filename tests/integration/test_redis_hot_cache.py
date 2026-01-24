"""
Integration tests for RedisHotCache with real Redis.

These tests require a running Redis instance.
They test the full hot cache functionality including:
- Event buffer (ring buffer) operations
- Context cache
- Goals cache
- Embedding cache
- Memory retrieval cache
- Distributed locks
- HotMemoryManager integration
"""

import pytest
import uuid
import time
from datetime import datetime

from vecna.memory.hot_cache import (
    RedisHotCache,
    CachedEvent,
    HotMemoryManager,
)


# ============================================================
# CACHED EVENT TESTS
# ============================================================


class TestCachedEvent:
    """Test CachedEvent dataclass."""

    def test_event_to_dict(self):
        """Test converting event to dictionary."""
        event = CachedEvent(
            id="test-123",
            event_type="test_event",
            payload={"key": "value"},
            session_id="session-456",
            created_at="2024-01-01T00:00:00",
        )

        d = event.to_dict()

        assert d["id"] == "test-123"
        assert d["event_type"] == "test_event"
        assert d["payload"]["key"] == "value"
        assert d["session_id"] == "session-456"

    def test_event_from_dict(self):
        """Test creating event from dictionary."""
        data = {
            "id": "test-789",
            "event_type": "another_event",
            "payload": {"action": "do_something"},
            "session_id": "session-abc",
            "created_at": "2024-01-02T12:00:00",
        }

        event = CachedEvent.from_dict(data)

        assert event.id == "test-789"
        assert event.event_type == "another_event"
        assert event.payload["action"] == "do_something"


# ============================================================
# EVENT BUFFER TESTS
# ============================================================


class TestEventBuffer:
    """Test event buffer (ring buffer) operations."""

    def test_push_event(self, redis_hot_cache: RedisHotCache):
        """Test pushing an event to the buffer."""
        event = CachedEvent(
            id=str(uuid.uuid4()),
            event_type="test_push",
            payload={"test": True},
            session_id="test-session",
            created_at=datetime.now().isoformat(),
        )

        result = redis_hot_cache.push_event(event)
        assert result is True

    def test_get_recent_events(self, redis_hot_cache: RedisHotCache):
        """Test retrieving recent events."""
        session_id = f"test-{uuid.uuid4()}"

        # Push some events
        for i in range(5):
            event = CachedEvent(
                id=str(uuid.uuid4()),
                event_type="test_recent",
                payload={"index": i, "session": session_id},
                session_id=session_id,
                created_at=datetime.now().isoformat(),
            )
            redis_hot_cache.push_event(event)

        # Get recent events
        events = redis_hot_cache.get_recent_events(limit=10)

        assert len(events) >= 5
        # Most recent should be first (LIFO)
        # Check that our events are in there
        our_events = [e for e in events if e.payload.get("session") == session_id]
        assert len(our_events) >= 5

    def test_get_events_with_type_filter(self, redis_hot_cache: RedisHotCache):
        """Test filtering events by type."""
        # Push events of different types
        for event_type in ["type_a", "type_b", "type_a", "type_c"]:
            event = CachedEvent(
                id=str(uuid.uuid4()),
                event_type=event_type,
                payload={"type": event_type},
                session_id="test-filter",
                created_at=datetime.now().isoformat(),
            )
            redis_hot_cache.push_event(event)

        # Filter by type
        type_a_events = redis_hot_cache.get_recent_events(limit=100, event_type="type_a")

        # All returned events should be type_a
        for event in type_a_events:
            assert event.event_type == "type_a"

    def test_event_buffer_limit(self, redis_hot_cache: RedisHotCache):
        """Test that event buffer respects max size."""
        # Push more events than the buffer limit
        original_max = redis_hot_cache.max_events

        # Temporarily set a small limit
        redis_hot_cache.max_events = 10

        for i in range(20):
            event = CachedEvent(
                id=str(uuid.uuid4()),
                event_type="limit_test",
                payload={"index": i},
                session_id="test-limit",
                created_at=datetime.now().isoformat(),
            )
            redis_hot_cache.push_event(event)

        # Buffer should be trimmed
        events = redis_hot_cache.get_recent_events(limit=100)
        limit_events = [e for e in events if e.event_type == "limit_test"]
        # Should have at most max_events (could have fewer if other events are in buffer)
        assert len(limit_events) <= 10

        # Restore original limit
        redis_hot_cache.max_events = original_max

    def test_clear_events(self, redis_hot_cache: RedisHotCache):
        """Test clearing the event buffer."""
        # Push some events
        for i in range(3):
            event = CachedEvent(
                id=str(uuid.uuid4()),
                event_type="clear_test",
                payload={"index": i},
                session_id="test-clear",
                created_at=datetime.now().isoformat(),
            )
            redis_hot_cache.push_event(event)

        # Clear events
        result = redis_hot_cache.clear_events()
        assert result is True

        # Buffer should be empty
        events = redis_hot_cache.get_recent_events(limit=100)
        assert len(events) == 0


# ============================================================
# CONTEXT CACHE TESTS
# ============================================================


class TestContextCache:
    """Test context cache operations."""

    def test_set_and_get_context(self, redis_hot_cache: RedisHotCache):
        """Test setting and getting context."""
        context = {
            "current_task": "Testing",
            "user_intent": "Verify functionality",
            "active_tools": ["search", "read"],
        }

        result = redis_hot_cache.set_context(context)
        assert result is True

        retrieved = redis_hot_cache.get_context()
        assert retrieved is not None
        assert retrieved["current_task"] == "Testing"
        assert "search" in retrieved["active_tools"]

    def test_update_context(self, redis_hot_cache: RedisHotCache):
        """Test updating context fields."""
        # Set initial context
        redis_hot_cache.set_context({"field1": "value1", "field2": "value2"})

        # Update specific fields
        redis_hot_cache.update_context({"field2": "updated", "field3": "new"})

        context = redis_hot_cache.get_context()
        assert context["field1"] == "value1"  # Unchanged
        assert context["field2"] == "updated"  # Updated
        assert context["field3"] == "new"  # Added

    def test_get_nonexistent_context(self, redis_hot_cache: RedisHotCache):
        """Test getting context when none exists."""
        # Clear any existing context first by setting a unique key
        redis_hot_cache._get_redis().delete(redis_hot_cache.CONTEXT_KEY)

        context = redis_hot_cache.get_context()
        assert context is None

    def test_context_ttl(self, redis_hot_cache: RedisHotCache):
        """Test that context expires after TTL."""
        # Set context with very short TTL
        redis_hot_cache.set_context({"test": "ttl"}, ttl=1)

        # Should exist immediately
        assert redis_hot_cache.get_context() is not None

        # Wait for expiry
        time.sleep(2)

        # Should be gone
        context = redis_hot_cache.get_context()
        assert context is None


# ============================================================
# GOALS CACHE TESTS
# ============================================================


class TestGoalsCache:
    """Test goals cache operations."""

    def test_set_and_get_goals(self, redis_hot_cache: RedisHotCache):
        """Test setting and getting active goals."""
        goals = [
            {"id": "goal-1", "content": "Complete testing", "priority": "high"},
            {"id": "goal-2", "content": "Write documentation", "priority": "medium"},
        ]

        result = redis_hot_cache.set_active_goals(goals)
        assert result is True

        retrieved = redis_hot_cache.get_active_goals()
        assert len(retrieved) == 2
        assert retrieved[0]["id"] == "goal-1"

    def test_get_empty_goals(self, redis_hot_cache: RedisHotCache):
        """Test getting goals when none set."""
        # Clear existing goals
        redis_hot_cache._get_redis().delete(redis_hot_cache.GOALS_KEY)

        goals = redis_hot_cache.get_active_goals()
        assert goals == []


# ============================================================
# EMBEDDING CACHE TESTS
# ============================================================


class TestEmbeddingCache:
    """Test embedding cache operations."""

    def test_set_and_get_embedding(self, redis_hot_cache: RedisHotCache):
        """Test caching and retrieving embeddings."""
        content = f"Test content for embedding {uuid.uuid4()}"
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

        result = redis_hot_cache.set_embedding(content, embedding)
        assert result is True

        retrieved = redis_hot_cache.get_embedding(content)
        assert retrieved is not None
        assert len(retrieved) == 5
        assert retrieved[0] == 0.1

    def test_get_nonexistent_embedding(self, redis_hot_cache: RedisHotCache):
        """Test getting embedding that doesn't exist."""
        content = f"Nonexistent content {uuid.uuid4()}"

        result = redis_hot_cache.get_embedding(content)
        assert result is None

    def test_set_and_get_embeddings_batch(self, redis_hot_cache: RedisHotCache):
        """Test batch embedding operations."""
        batch_id = str(uuid.uuid4())[:8]
        embeddings = {
            f"Content A {batch_id}": [0.1, 0.2, 0.3],
            f"Content B {batch_id}": [0.4, 0.5, 0.6],
            f"Content C {batch_id}": [0.7, 0.8, 0.9],
        }

        # Set batch
        result = redis_hot_cache.set_embeddings_batch(embeddings)
        assert result is True

        # Get batch
        contents = list(embeddings.keys())
        retrieved = redis_hot_cache.get_embeddings_batch(contents)

        assert len(retrieved) == 3
        for content, embedding in retrieved.items():
            assert embedding is not None
            assert len(embedding) == 3

    def test_embedding_cache_partial_hit(self, redis_hot_cache: RedisHotCache):
        """Test batch retrieval with some missing embeddings."""
        batch_id = str(uuid.uuid4())[:8]

        # Cache only one embedding
        cached_content = f"Cached {batch_id}"
        redis_hot_cache.set_embedding(cached_content, [1.0, 2.0, 3.0])

        # Request both cached and uncached
        contents = [cached_content, f"Not cached {batch_id}"]
        results = redis_hot_cache.get_embeddings_batch(contents)

        assert results[cached_content] is not None
        assert results[f"Not cached {batch_id}"] is None


# ============================================================
# MEMORY RETRIEVAL CACHE TESTS
# ============================================================


class TestMemoryRetrievalCache:
    """Test memory retrieval cache operations."""

    def test_set_and_get_cached_retrieval(self, redis_hot_cache: RedisHotCache):
        """Test caching and retrieving query results."""
        query = f"What is Python? {uuid.uuid4()}"
        result = "Python is a programming language known for its simplicity."

        success = redis_hot_cache.set_cached_retrieval(query, result)
        assert success is True

        retrieved = redis_hot_cache.get_cached_retrieval(query)
        assert retrieved == result

    def test_get_nonexistent_retrieval(self, redis_hot_cache: RedisHotCache):
        """Test getting retrieval that doesn't exist."""
        query = f"Nonexistent query {uuid.uuid4()}"

        result = redis_hot_cache.get_cached_retrieval(query)
        assert result is None

    def test_retrieval_cache_ttl(self, redis_hot_cache: RedisHotCache):
        """Test that retrieval cache expires."""
        query = f"TTL test query {uuid.uuid4()}"

        # Set with very short TTL
        redis_hot_cache.set_cached_retrieval(query, "Short-lived result", ttl=1)

        # Should exist immediately
        assert redis_hot_cache.get_cached_retrieval(query) is not None

        # Wait for expiry
        time.sleep(2)

        # Should be gone
        assert redis_hot_cache.get_cached_retrieval(query) is None


# ============================================================
# DISTRIBUTED LOCK TESTS
# ============================================================


class TestDistributedLocks:
    """Test distributed lock operations."""

    def test_acquire_and_release_lock(self, redis_hot_cache: RedisHotCache):
        """Test acquiring and releasing a lock."""
        resource = f"test-resource-{uuid.uuid4()}"

        with redis_hot_cache.lock(resource, ttl=10):
            # Lock is held
            assert redis_hot_cache.is_locked(resource) is True

        # Lock is released
        assert redis_hot_cache.is_locked(resource) is False

    def test_lock_blocks_others(self, redis_hot_cache: RedisHotCache):
        """Test that lock blocks concurrent access."""
        resource = f"blocking-resource-{uuid.uuid4()}"

        # Acquire lock
        with redis_hot_cache.lock(resource, ttl=10):
            # Try to acquire same lock non-blocking
            try:
                with redis_hot_cache.lock(resource, blocking=False):
                    # Should not reach here
                    assert False, "Should not acquire lock"
            except TimeoutError:
                # Expected - lock is held
                pass

    def test_lock_timeout(self, redis_hot_cache: RedisHotCache):
        """Test lock timeout when waiting."""
        resource = f"timeout-resource-{uuid.uuid4()}"

        # Hold the lock
        r = redis_hot_cache._get_redis()
        r.set(f"{redis_hot_cache.LOCK_PREFIX}{resource}", "holder", ex=30)

        # Try to acquire with short timeout
        start = time.time()
        try:
            with redis_hot_cache.lock(resource, blocking=True, timeout=1):
                assert False, "Should not acquire lock"
        except TimeoutError:
            elapsed = time.time() - start
            # Should have waited approximately timeout seconds
            assert elapsed >= 0.9

        # Clean up
        r.delete(f"{redis_hot_cache.LOCK_PREFIX}{resource}")

    def test_is_locked(self, redis_hot_cache: RedisHotCache):
        """Test checking if resource is locked."""
        resource = f"check-lock-{uuid.uuid4()}"

        assert redis_hot_cache.is_locked(resource) is False

        with redis_hot_cache.lock(resource, ttl=10):
            assert redis_hot_cache.is_locked(resource) is True

        assert redis_hot_cache.is_locked(resource) is False


# ============================================================
# STATS AND MANAGEMENT TESTS
# ============================================================


class TestStatsAndManagement:
    """Test statistics and management operations."""

    def test_get_stats(self, redis_hot_cache: RedisHotCache):
        """Test retrieving cache statistics."""
        stats = redis_hot_cache.get_stats()

        assert "connected" in stats
        assert stats["connected"] is True
        assert "event_count" in stats
        assert "cached_embeddings" in stats
        assert "redis_memory_used" in stats

    def test_clear_all(self, redis_hot_cache: RedisHotCache):
        """Test clearing all cache data."""
        # Add some data
        redis_hot_cache.set_context({"test": "data"})
        redis_hot_cache.set_embedding("test content", [1.0, 2.0, 3.0])

        event = CachedEvent(
            id=str(uuid.uuid4()),
            event_type="test",
            payload={},
            session_id="test",
            created_at=datetime.now().isoformat(),
        )
        redis_hot_cache.push_event(event)

        # Clear all
        result = redis_hot_cache.clear_all()
        assert result is True

        # Verify cleared
        stats = redis_hot_cache.get_stats()
        assert stats["event_count"] == 0


# ============================================================
# HOT MEMORY MANAGER TESTS
# ============================================================


class TestHotMemoryManager:
    """Test HotMemoryManager integration."""

    @pytest.fixture
    def hot_memory_manager(self, redis_available, postgres_available):
        """Get a HotMemoryManager instance."""
        if not redis_available:
            pytest.skip("Redis not available")
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import os

        manager = HotMemoryManager(
            redis_url=os.environ.get("VECNA_REDIS_URL"),
            pg_url=os.environ.get("VECNA_PG_URL"),
        )
        yield manager
        manager.close()

    def test_push_event_with_persist(self, hot_memory_manager: HotMemoryManager):
        """Test pushing event to both cache and PG."""
        event_id = hot_memory_manager.push_event(
            event_type="test_persist",
            payload={"action": "test", "value": 123},
            session_id=f"test-session-{uuid.uuid4()}",
            persist=True,
        )

        assert event_id is not None

    def test_push_event_without_persist(self, hot_memory_manager: HotMemoryManager):
        """Test pushing event to cache only."""
        event_id = hot_memory_manager.push_event(
            event_type="test_no_persist",
            payload={"action": "test"},
            session_id="test-session",
            persist=False,
        )

        # Event ID is generated even without persistence
        assert event_id is not None

    def test_get_embedding_cached(self, hot_memory_manager: HotMemoryManager):
        """Test getting embedding with caching."""
        content = f"Unique content for embedding test {uuid.uuid4()}"

        # First call - should generate and cache
        emb1 = hot_memory_manager.get_embedding_cached(content)
        assert emb1 is not None
        assert len(emb1) in [384, 1536]

        # Second call - should use cache
        emb2 = hot_memory_manager.get_embedding_cached(content)
        assert emb2 is not None
        assert emb1 == emb2

    def test_retrieve_with_cache(self, hot_memory_manager: HotMemoryManager):
        """Test retrieval with caching."""
        query = f"Test query for retrieval {uuid.uuid4()}"

        # First call - queries PG and caches
        result1 = hot_memory_manager.retrieve_with_cache(query, max_items=5, cache_ttl=60)

        assert isinstance(result1, str)

        # Second call - should use cache
        result2 = hot_memory_manager.retrieve_with_cache(query, max_items=5)

        assert result1 == result2

    def test_get_combined_stats(self, hot_memory_manager: HotMemoryManager):
        """Test getting combined stats from hot and warm storage."""
        stats = hot_memory_manager.get_stats()

        assert "hot_cache" in stats
        assert "warm_storage" in stats
        assert stats["hot_cache"]["connected"] is True


# ============================================================
# CONNECTION HANDLING TESTS
# ============================================================


class TestConnectionHandling:
    """Test connection handling and resilience."""

    def test_connection_reuse(self, redis_hot_cache: RedisHotCache):
        """Test that connections are reused."""
        # Multiple operations should use same connection
        redis_hot_cache.set_context({"test": 1})
        redis_hot_cache.set_context({"test": 2})
        redis_hot_cache.get_context()

        # Internal connection should be the same
        conn1 = redis_hot_cache._redis
        redis_hot_cache.get_context()
        conn2 = redis_hot_cache._redis

        assert conn1 is conn2

    def test_close_connection(self, redis_available):
        """Test closing connection."""
        if not redis_available:
            pytest.skip("Redis not available")

        import os

        cache = RedisHotCache(redis_url=os.environ.get("VECNA_REDIS_URL"))

        # Force connection
        cache.get_stats()
        assert cache._redis is not None

        # Close
        cache.close()
        assert cache._redis is None

    def test_reconnect_after_close(self, redis_available):
        """Test reconnecting after close."""
        if not redis_available:
            pytest.skip("Redis not available")

        import os

        cache = RedisHotCache(redis_url=os.environ.get("VECNA_REDIS_URL"))

        # Use, close, use again
        cache.set_context({"test": "before"})
        cache.close()

        # Should reconnect automatically
        cache.set_context({"test": "after"})
        result = cache.get_context()

        assert result["test"] == "after"
        cache.close()
