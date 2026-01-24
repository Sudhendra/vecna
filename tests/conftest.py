"""
Global pytest fixtures for Vecna test suite.

This module provides fixtures for:
- PostgreSQL database connections (real)
- Redis cache connections (real)
- HiveState instances
- Memory stores
- Adapters
- CLI test runners
"""

import os
import pytest
import asyncio
from typing import Generator, Optional
from datetime import datetime

# Ensure environment variables are loaded
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

# Database URLs from environment
PG_URL = os.environ.get("VECNA_PG_URL", "postgresql://vecna:thehiveremembers@localhost:5432/vecna")
REDIS_URL = os.environ.get("VECNA_REDIS_URL", "redis://localhost:6379/0")


# ============================================================
# ASYNC EVENT LOOP
# ============================================================


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ============================================================
# POSTGRESQL FIXTURES
# ============================================================


@pytest.fixture(scope="session")
def postgres_available() -> bool:
    """Check if PostgreSQL is available and accessible."""
    try:
        import psycopg2

        conn = psycopg2.connect(PG_URL)
        conn.close()
        return True
    except Exception as e:
        print(f"PostgreSQL not available: {e}")
        return False


@pytest.fixture
def postgres_db(postgres_available):
    """
    Get a PostgreSQL connection for testing.

    Skips the test if PostgreSQL is not available.
    """
    if not postgres_available:
        pytest.skip("PostgreSQL not available")

    import psycopg2

    conn = psycopg2.connect(PG_URL)
    yield conn
    conn.close()


@pytest.fixture
def pg_memory_store(postgres_available):
    """
    Get a PgMemoryStore instance for testing.

    Uses real PostgreSQL connection.
    """
    if not postgres_available:
        pytest.skip("PostgreSQL not available")

    from vecna.memory.pg_store import PgMemoryStore

    store = PgMemoryStore(connection_string=PG_URL)
    yield store
    # Cleanup: close connection
    if hasattr(store, "_conn") and store._conn:
        store._conn.close()


@pytest.fixture
def pg_state_manager(postgres_available):
    """
    Get a PgStateManager instance for testing.

    Uses real PostgreSQL connection.
    """
    if not postgres_available:
        pytest.skip("PostgreSQL not available")

    from vecna.core.state_store import PgStateManager

    manager = PgStateManager(pg_url=PG_URL)
    yield manager
    # Cleanup
    if hasattr(manager, "_conn") and manager._conn:
        manager._conn.close()


# ============================================================
# REDIS FIXTURES
# ============================================================


@pytest.fixture(scope="session")
def redis_available() -> bool:
    """Check if Redis is available and accessible."""
    try:
        import redis

        r = redis.from_url(REDIS_URL, decode_responses=True)
        r.ping()
        r.close()
        return True
    except Exception as e:
        print(f"Redis not available: {e}")
        return False


@pytest.fixture
def redis_client(redis_available):
    """
    Get a Redis client for testing.

    Skips the test if Redis is not available.
    """
    if not redis_available:
        pytest.skip("Redis not available")

    import redis

    client = redis.from_url(REDIS_URL, decode_responses=True)
    yield client
    client.close()


@pytest.fixture
def redis_hot_cache(redis_available):
    """
    Get a RedisHotCache instance for testing.

    Uses real Redis connection.
    """
    if not redis_available:
        pytest.skip("Redis not available")

    from vecna.memory.hot_cache import RedisHotCache

    cache = RedisHotCache(redis_url=REDIS_URL)
    yield cache
    # Cleanup: clear test keys and close
    try:
        cache.clear_all()
    except Exception:
        pass
    cache.close()


# ============================================================
# DOCKER FIXTURES
# ============================================================


@pytest.fixture(scope="session")
def docker_available() -> bool:
    """Check if Docker daemon is running."""
    try:
        import subprocess

        result = subprocess.run(["docker", "info"], capture_output=True, timeout=10)
        return result.returncode == 0
    except Exception as e:
        print(f"Docker not available: {e}")
        return False


# ============================================================
# COPILOT AUTH FIXTURES
# ============================================================


@pytest.fixture(scope="session")
def copilot_authenticated() -> bool:
    """Check if GitHub Copilot authentication is available."""
    try:
        from vecna.auth.copilot import get_copilot_auth

        auth = get_copilot_auth()
        # Check if token file exists
        return auth.token_path.exists()
    except Exception as e:
        print(f"Copilot auth not available: {e}")
        return False


# ============================================================
# OPENAI FIXTURES (for embeddings)
# ============================================================


@pytest.fixture(scope="session")
def openai_available() -> bool:
    """Check if OpenAI API key is available for embeddings."""
    return bool(os.environ.get("OPENAI_API_KEY"))


# ============================================================
# HIVE STATE FIXTURES
# ============================================================


@pytest.fixture
def clean_state():
    """
    Get a fresh HiveState instance for testing.

    Provides a clean slate for each test.
    """
    from vecna.core.hive_state import HiveState

    state = HiveState()
    state.ensure_identity()  # Initialize identity
    return state


@pytest.fixture
def populated_state():
    """
    Get a HiveState with some pre-populated data.

    Contains facts, beliefs, hypotheses for testing operations.
    """
    import uuid
    from vecna.core.hive_state import HiveState
    from vecna.core.types import Fact, Belief, Hypothesis, Goal, OpenQuestion

    state = HiveState()
    state.ensure_identity()

    # Use unique IDs to avoid conflicts with existing data
    batch_id = str(uuid.uuid4())[:8]

    # Add sample facts
    state.add_fact(
        Fact(
            content=f"Python is a programming language [{batch_id}]",
            confidence=0.9,
            source_model="test",
            domain="code",
        )
    )
    state.add_fact(
        Fact(
            content=f"The sky is blue due to Rayleigh scattering [{batch_id}]",
            confidence=0.85,
            source_model="test",
            domain="science",
        )
    )
    state.add_fact(
        Fact(
            content=f"2 + 2 equals 4 [{batch_id}]",
            confidence=1.0,
            source_model="test",
            domain="math",
        )
    )

    # Add sample beliefs
    state.add_belief(
        Belief(
            content=f"Test-driven development improves code quality [{batch_id}]",
            confidence=0.7,
            source_model="test",
            reasoning="Based on empirical studies",
        )
    )

    # Add sample hypothesis
    state.add_hypothesis(
        Hypothesis(
            content=f"Parallel processing could improve response time [{batch_id}]",
            confidence=0.4,
            source_model="test",
            exploration_notes="Needs benchmarking",
        )
    )

    # Add sample goal
    state.add_goal(Goal(content=f"Complete test implementation [{batch_id}]", priority="high"))

    # Add sample question
    state.add_open_question(
        OpenQuestion(
            question=f"What is the optimal batch size for embeddings? [{batch_id}]",
            priority="medium",
        )
    )

    return state


# ============================================================
# CONSENSUS ENGINE FIXTURES
# ============================================================


@pytest.fixture
def consensus_engine():
    """Get a ConsensusEngine instance for testing."""
    from vecna.orchestrator.consensus import ConsensusEngine, ConsensusConfig

    config = ConsensusConfig(
        min_fact_confidence=0.3,
        min_belief_confidence=0.2,
        agreement_boost=0.15,
        similarity_threshold=0.7,
    )
    return ConsensusEngine(config)


# ============================================================
# ADAPTER FIXTURES
# ============================================================


@pytest.fixture
def model_config():
    """Get a sample ModelConfig for testing."""
    from vecna.adapters.base import ModelConfig

    return ModelConfig(
        name="test-model",
        model_id="gpt-4o",
        domain="general",
        weight=1.0,
        temperature=0.7,
        max_tokens=4096,
    )


@pytest.fixture
def copilot_adapter(copilot_authenticated, model_config):
    """
    Get a CopilotAdapter instance for testing.

    Requires Copilot authentication.
    """
    if not copilot_authenticated:
        pytest.skip("Copilot authentication not available")

    from vecna.adapters.base import CopilotAdapter

    return CopilotAdapter(model_config)


# ============================================================
# CLI FIXTURES
# ============================================================


@pytest.fixture
def cli_runner():
    """Get a Click test runner."""
    from click.testing import CliRunner

    return CliRunner()


@pytest.fixture
def tty_cli_runner():
    """
    Get a Click test runner with TTY simulation.

    For testing TUI and interactive features.
    """
    from click.testing import CliRunner

    # mix_stderr=False helps with Rich console output capture
    return CliRunner(mix_stderr=False)


# ============================================================
# MEMORY EVENT FIXTURES
# ============================================================


@pytest.fixture
def sample_memory_item():
    """Get a sample MemoryItem for testing."""
    from vecna.memory.pg_store import MemoryItem

    return MemoryItem(
        content="This is a test memory item for unit testing",
        item_type="fact",
        confidence=0.8,
        domain="general",
        source_model="test",
        metadata={"test": True},
    )


@pytest.fixture
def sample_cached_event():
    """Get a sample CachedEvent for testing."""
    from vecna.memory.hot_cache import CachedEvent

    return CachedEvent(
        id="test-event-123",
        event_type="test_event",
        payload={"action": "test", "value": 42},
        session_id="test-session",
        created_at=datetime.now().isoformat(),
    )


# ============================================================
# HIVE UPDATE FIXTURES
# ============================================================


@pytest.fixture
def sample_hive_update():
    """Get a sample HiveUpdate for testing consensus."""
    from vecna.core.types import HiveUpdate

    return HiveUpdate(
        source_model="test-model",
        new_facts=[
            {"content": "Test fact 1", "confidence": 0.8, "domain": "general"},
            {"content": "Test fact 2", "confidence": 0.7, "domain": "code"},
        ],
        belief_changes=[
            {"content": "Test belief", "confidence": 0.6, "reasoning": "Test reasoning"}
        ],
        new_hypotheses=[{"content": "Test hypothesis", "confidence": 0.3, "notes": "Explore this"}],
        open_questions=[{"question": "What should we test?", "priority": "high"}],
        contradictions_found=[],
        confidence=0.75,
    )


# ============================================================
# CLEANUP UTILITIES
# ============================================================


@pytest.fixture
def cleanup_test_data(postgres_available, redis_available):
    """
    Fixture to clean up test data after tests.

    Yields to run the test, then cleans up.
    """
    yield

    # Cleanup PostgreSQL test data
    if postgres_available:
        try:
            import psycopg2

            conn = psycopg2.connect(PG_URL)
            with conn.cursor() as cur:
                # Delete test items (items with source_model='test')
                cur.execute("DELETE FROM memory_items WHERE source_model = 'test'")
                cur.execute("DELETE FROM memory_events WHERE session_id LIKE 'test-%'")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"PostgreSQL cleanup failed: {e}")

    # Cleanup Redis test data
    if redis_available:
        try:
            import redis

            r = redis.from_url(REDIS_URL, decode_responses=True)
            # Delete test keys
            test_keys = r.keys("vecna:test:*")
            if test_keys:
                r.delete(*test_keys)
            r.close()
        except Exception as e:
            print(f"Redis cleanup failed: {e}")


# ============================================================
# MARKERS AUTO-APPLICATION
# ============================================================


def pytest_collection_modifyitems(config, items):
    """
    Automatically apply markers based on test location.
    """
    for item in items:
        # Apply markers based on test path
        if "/unit/" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)

        # Apply markers based on fixture usage
        if "postgres_db" in item.fixturenames or "pg_memory_store" in item.fixturenames:
            item.add_marker(pytest.mark.requires_postgres)
        if "redis_client" in item.fixturenames or "redis_hot_cache" in item.fixturenames:
            item.add_marker(pytest.mark.requires_redis)
        if "docker_available" in item.fixturenames:
            item.add_marker(pytest.mark.requires_docker)
        if "copilot_adapter" in item.fixturenames:
            item.add_marker(pytest.mark.requires_copilot)
