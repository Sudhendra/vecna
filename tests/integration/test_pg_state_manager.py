"""
Integration tests for PgStateManager with real PostgreSQL and Redis.

These tests require running PostgreSQL and Redis instances.
They test the full state management functionality including:
- State persistence (save/load)
- Memory synchronization
- Redis caching operations
- Offline spool fallback
- Combined statistics
"""

import pytest
import uuid

from vecna.core.state_store import PgStateManager, PostgresStore
from vecna.core.hive_state import HiveState
from vecna.core.types import Fact, Belief, Hypothesis


# ============================================================
# POSTGRES STORE TESTS
# ============================================================


class TestPostgresStore:
    """Test PostgresStore directly."""

    def test_save_and_load_state(self, postgres_available):
        """Test saving and loading state."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import os

        store = PostgresStore(connection_string=os.environ.get("VECNA_PG_URL"))

        key = f"test-{uuid.uuid4()}"

        # Create state
        state = HiveState()
        state.ensure_identity()
        state.add_fact(
            Fact(
                content="Test fact for persistence",
                confidence=0.9,
                source_model="test",
                domain="test",
            )
        )

        # Save
        result = store.save(state, key)
        assert result is True

        # Load
        loaded = store.load(key)
        assert loaded is not None
        assert len(loaded.facts) >= 1

        # Cleanup
        store.delete(key)
        store.close()

    def test_exists(self, postgres_available):
        """Test checking if state exists."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import os

        store = PostgresStore(connection_string=os.environ.get("VECNA_PG_URL"))

        key = f"test-exists-{uuid.uuid4()}"

        # Should not exist initially
        assert store.exists(key) is False

        # Save state
        state = HiveState()
        store.save(state, key)

        # Should exist now
        assert store.exists(key) is True

        # Cleanup
        store.delete(key)
        store.close()

    def test_delete(self, postgres_available):
        """Test deleting state."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import os

        store = PostgresStore(connection_string=os.environ.get("VECNA_PG_URL"))

        key = f"test-delete-{uuid.uuid4()}"

        # Save state
        state = HiveState()
        store.save(state, key)
        assert store.exists(key) is True

        # Delete
        result = store.delete(key)
        assert result is True
        assert store.exists(key) is False

        store.close()

    def test_list_keys(self, postgres_available):
        """Test listing state keys."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import os

        store = PostgresStore(connection_string=os.environ.get("VECNA_PG_URL"))

        prefix = f"test-list-{str(uuid.uuid4())[:8]}"
        keys = [f"{prefix}-1", f"{prefix}-2", f"{prefix}-3"]

        # Save multiple states
        state = HiveState()
        for key in keys:
            store.save(state, key)

        # List keys
        all_keys = store.list_keys()

        # Our keys should be in the list
        for key in keys:
            assert key in all_keys

        # Cleanup
        for key in keys:
            store.delete(key)
        store.close()

    def test_get_metadata(self, postgres_available):
        """Test getting state metadata."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import os

        store = PostgresStore(connection_string=os.environ.get("VECNA_PG_URL"))

        key = f"test-metadata-{uuid.uuid4()}"

        # Create state with known content
        state = HiveState()
        state.ensure_identity()
        state.add_fact(Fact(content="Fact 1", confidence=0.9, source_model="test"))
        state.add_fact(Fact(content="Fact 2", confidence=0.8, source_model="test"))
        state.add_belief(Belief(content="Belief 1", confidence=0.7, source_model="test"))

        store.save(state, key)

        # Get metadata
        metadata = store.get_metadata(key)

        assert metadata is not None
        assert metadata["num_facts"] == 2
        assert metadata["num_beliefs"] == 1
        assert "version" in metadata
        assert "created_at" in metadata

        # Cleanup
        store.delete(key)
        store.close()

    def test_update_existing_state(self, postgres_available):
        """Test updating an existing state."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import os

        store = PostgresStore(connection_string=os.environ.get("VECNA_PG_URL"))

        key = f"test-update-{uuid.uuid4()}"

        # Create and save initial state
        state = HiveState()
        state.add_fact(Fact(content="Initial fact", confidence=0.8, source_model="test"))
        store.save(state, key)

        # Load, modify, and save again
        loaded = store.load(key)
        loaded.add_fact(Fact(content="Additional fact", confidence=0.9, source_model="test"))
        store.save(loaded, key)

        # Load again and verify
        final = store.load(key)
        assert len(final.facts) == 2

        # Cleanup
        store.delete(key)
        store.close()


# ============================================================
# PG STATE MANAGER TESTS
# ============================================================


class TestPgStateManager:
    """Test PgStateManager unified interface."""

    def test_init(self, postgres_available):
        """Test manager initialization."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import os

        manager = PgStateManager(pg_url=os.environ.get("VECNA_PG_URL"))
        assert manager is not None
        assert manager.pg_url is not None

    def test_load_state(self, pg_state_manager: PgStateManager):
        """Test loading state."""
        key = f"test-load-{uuid.uuid4()}"

        # Initially should be None
        _ = pg_state_manager.load_state(key)
        # May be None or return existing state

        # Save a new state
        new_state = HiveState()
        new_state.ensure_identity()
        pg_state_manager.save_state(new_state, key)

        # Now should load
        loaded = pg_state_manager.load_state(key)
        assert loaded is not None

        # Cleanup
        pg_state_manager._get_pg_store().delete(key)

    def test_save_state(self, pg_state_manager: PgStateManager):
        """Test saving state."""
        key = f"test-save-{uuid.uuid4()}"

        state = HiveState()
        state.ensure_identity()
        state.add_fact(
            Fact(
                content="Manager test fact",
                confidence=0.85,
                source_model="test",
                domain="test",
            )
        )

        result = pg_state_manager.save_state(state, key)
        assert result is True

        # Verify it was saved
        loaded = pg_state_manager.load_state(key)
        assert loaded is not None
        assert len(loaded.facts) >= 1

        # Cleanup
        pg_state_manager._get_pg_store().delete(key)

    def test_check_pg_available(self, pg_state_manager: PgStateManager):
        """Test PostgreSQL availability check."""
        available = pg_state_manager._check_pg_available()
        assert available is True

    def test_get_state_metadata(self, pg_state_manager: PgStateManager):
        """Test getting state metadata through manager."""
        key = f"test-meta-mgr-{uuid.uuid4()}"

        # Create state with specific content
        state = HiveState()
        state.add_hypothesis(
            Hypothesis(content="Test hypothesis", confidence=0.5, source_model="test")
        )

        pg_state_manager.save_state(state, key)

        # Get metadata via underlying store
        metadata = pg_state_manager._get_pg_store().get_metadata(key)
        assert metadata is not None
        assert metadata["num_hypotheses"] == 1

        # Cleanup
        pg_state_manager._get_pg_store().delete(key)


# ============================================================
# REDIS CACHING TESTS
# ============================================================


class TestPgStateManagerRedis:
    """Test PgStateManager Redis caching operations."""

    @pytest.fixture
    def manager_with_redis(self, postgres_available, redis_available):
        """Get manager with Redis configured."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")
        if not redis_available:
            pytest.skip("Redis not available")

        import os

        manager = PgStateManager(
            pg_url=os.environ.get("VECNA_PG_URL"),
            redis_url=os.environ.get("VECNA_REDIS_URL"),
        )
        yield manager

    def test_check_redis_available(self, manager_with_redis: PgStateManager):
        """Test Redis availability check."""
        available = manager_with_redis._check_redis_available()
        assert available is True

    def test_cache_and_get_embedding(self, manager_with_redis: PgStateManager):
        """Test embedding caching."""
        content = f"Test content for embedding {uuid.uuid4()}"
        embedding = [0.1, 0.2, 0.3, 0.4, 0.5]

        # Should be None initially
        cached = manager_with_redis.get_cached_embedding(content)
        assert cached is None

        # Cache it
        result = manager_with_redis.cache_embedding(content, embedding)
        assert result is True

        # Should be retrievable now
        cached = manager_with_redis.get_cached_embedding(content)
        assert cached is not None
        assert len(cached) == 5

    def test_cache_and_get_retrieval(self, manager_with_redis: PgStateManager):
        """Test retrieval caching."""
        query = f"Test query {uuid.uuid4()}"
        result = "This is the cached retrieval result."

        # Should be None initially
        cached = manager_with_redis.get_cached_retrieval(query)
        assert cached is None

        # Cache it
        success = manager_with_redis.cache_retrieval(query, result)
        assert success is True

        # Should be retrievable now
        cached = manager_with_redis.get_cached_retrieval(query)
        assert cached == result

    def test_push_event_to_cache(self, manager_with_redis: PgStateManager):
        """Test pushing events to cache."""
        result = manager_with_redis.push_event_to_cache(
            event_type="test_event",
            payload={"action": "test", "value": 42},
            session_id="test-session",
        )
        assert result is True

    def test_get_redis_stats(self, manager_with_redis: PgStateManager):
        """Test getting Redis stats."""
        stats = manager_with_redis.get_redis_stats()

        assert "connected" in stats
        assert stats["connected"] is True


# ============================================================
# MEMORY SYNC TESTS
# ============================================================


class TestMemorySynchronization:
    """Test memory synchronization operations."""

    @pytest.fixture
    def manager_with_memory(self, postgres_available, redis_available):
        """Get manager configured for memory sync with mock embedder."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import os
        from tests.conftest import mock_embedder, MOCK_EMBEDDING_DIM

        manager = PgStateManager(
            pg_url=os.environ.get("VECNA_PG_URL"),
            redis_url=os.environ.get("VECNA_REDIS_URL") if redis_available else None,
            auto_sync_memory=False,  # We'll test manual sync
        )

        # Inject mock embedder into the memory store so tests don't need OpenAI
        store = manager._get_memory_store()
        if store is not None:
            store._custom_embedder = mock_embedder
            store.embedding_dim = MOCK_EMBEDDING_DIM

        yield manager

    def test_get_memory_store(self, manager_with_memory: PgStateManager):
        """Test getting memory store."""
        store = manager_with_memory._get_memory_store()
        assert store is not None

    def test_sync_memory_from_state(self, manager_with_memory: PgStateManager):
        """Test syncing memory from state."""
        # Create state with content
        state = HiveState()
        state.ensure_identity()
        state.add_fact(
            Fact(
                content=f"Sync test fact {uuid.uuid4()}",
                confidence=0.9,
                source_model="test",
                domain="test",
            )
        )
        state.add_belief(
            Belief(
                content=f"Sync test belief {uuid.uuid4()}",
                confidence=0.7,
                source_model="test",
            )
        )

        # Sync to memory
        store = manager_with_memory._get_memory_store()
        if store is not None:
            counts = store.add_from_state(state)
            assert isinstance(counts, dict)
            # Should have synced some items
            total = sum(counts.values())
            assert total >= 2


# ============================================================
# AUTO-SYNC TESTS
# ============================================================


class TestAutoSync:
    """Test automatic memory synchronization."""

    def test_auto_sync_on_save(self, postgres_available, redis_available):
        """Test that auto_sync_memory triggers on save."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import os

        manager = PgStateManager(
            pg_url=os.environ.get("VECNA_PG_URL"),
            redis_url=os.environ.get("VECNA_REDIS_URL") if redis_available else None,
            auto_sync_memory=True,
        )

        key = f"test-autosync-{uuid.uuid4()}"

        state = HiveState()
        state.ensure_identity()
        state.add_fact(
            Fact(
                content=f"Auto-sync fact {uuid.uuid4()}",
                confidence=0.9,
                source_model="test",
            )
        )

        # Save with auto-sync enabled
        result = manager.save_state(state, key)
        assert result is True

        # Cleanup
        manager._get_pg_store().delete(key)


# ============================================================
# COMBINED STATS TESTS
# ============================================================


class TestCombinedStats:
    """Test combined statistics retrieval."""

    def test_get_combined_stats(self, pg_state_manager: PgStateManager):
        """Test getting combined stats from all stores."""
        # The manager should be able to report status
        pg_available = pg_state_manager._check_pg_available()
        assert pg_available is True

        # Get Redis stats (may not be connected)
        redis_stats = pg_state_manager.get_redis_stats()
        assert "connected" in redis_stats


# ============================================================
# CONNECTION HANDLING TESTS
# ============================================================


class TestConnectionHandling:
    """Test connection handling and resilience."""

    def test_connection_reuse(self, postgres_available):
        """Test that connections are reused."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import os

        manager = PgStateManager(pg_url=os.environ.get("VECNA_PG_URL"))

        # Multiple operations should use same connection
        manager._check_pg_available()
        store1 = manager._get_pg_store()

        manager._check_pg_available()
        store2 = manager._get_pg_store()

        assert store1 is store2

    def test_lazy_initialization(self, postgres_available):
        """Test that stores are lazily initialized."""
        if not postgres_available:
            pytest.skip("PostgreSQL not available")

        import os

        manager = PgStateManager(pg_url=os.environ.get("VECNA_PG_URL"))

        # Stores should be None initially
        assert manager._pg_store is None
        assert manager._memory_store is None

        # Access forces initialization
        _ = manager._get_pg_store()
        assert manager._pg_store is not None
