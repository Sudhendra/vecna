"""
StateStore: Abstract interface for HiveState persistence.

This module provides:
1. Abstract StateStore interface
2. PostgresStore implementation (the only supported backend)
3. OfflineSpoolStore for handling PG connectivity issues
4. Factory function for creating stores

PostgreSQL + Redis is the ONLY supported storage backend.
All state persistence flows through PostgreSQL with Redis caching.
"""

from __future__ import annotations

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from pathlib import Path
from datetime import datetime
import json
import logging
import os

from vecna.core.hive_state import HiveState

if TYPE_CHECKING:
    from vecna.core.types import IdentityEvent

logger = logging.getLogger("vecna.state_store")


class StateStore(ABC):
    """
    Abstract interface for HiveState persistence.

    All state storage backends must implement this interface.
    PostgresStore is the canonical implementation.
    """

    @abstractmethod
    def save(self, state: HiveState, key: str = "default") -> bool:
        """
        Persist the HiveState.

        Args:
            state: The HiveState to save
            key: Optional key/identifier for the state (default: "default")

        Returns:
            True if save succeeded, False otherwise
        """
        pass

    @abstractmethod
    def load(self, key: str = "default") -> Optional[HiveState]:
        """
        Load a HiveState from storage.

        Args:
            key: The key/identifier for the state (default: "default")

        Returns:
            HiveState if found, None otherwise
        """
        pass

    @abstractmethod
    def exists(self, key: str = "default") -> bool:
        """
        Check if a state exists in storage.

        Args:
            key: The key/identifier to check

        Returns:
            True if state exists, False otherwise
        """
        pass

    @abstractmethod
    def delete(self, key: str = "default") -> bool:
        """
        Delete a state from storage.

        Args:
            key: The key/identifier to delete

        Returns:
            True if deletion succeeded, False otherwise
        """
        pass

    @abstractmethod
    def list_keys(self) -> List[str]:
        """
        List all available state keys.

        Returns:
            List of state keys/identifiers
        """
        pass

    def get_metadata(self, key: str = "default") -> Optional[Dict[str, Any]]:
        """
        Get metadata about a stored state without loading the full state.

        Default implementation loads the full state. Backends can override
        for more efficient metadata retrieval.

        Args:
            key: The key/identifier

        Returns:
            Dict with metadata (version, updated_at, etc.) or None
        """
        state = self.load(key)
        if state is None:
            return None
        return state.to_summary_dict()


class PostgresStore(StateStore):
    """
    PostgreSQL-based state storage.

    Production-ready implementation using PostgreSQL for:
    - Multi-process Vecna support
    - Durable hive state persistence
    - Efficient metadata queries

    Requires the `psycopg2` package and a running PostgreSQL instance.
    """

    def __init__(self, connection_string: Optional[str] = None):
        """
        Initialize PostgreSQL store.

        Args:
            connection_string: PostgreSQL connection URL.
                Format: postgresql://user:password@host:port/database
                If None, reads from VECNA_PG_URL environment variable.
        """
        self.connection_string = connection_string or os.environ.get("VECNA_PG_URL")
        if not self.connection_string:
            raise ValueError(
                "PostgresStore requires a connection string. "
                "Pass it directly or set VECNA_PG_URL environment variable."
            )

        # Lazy connection - don't connect until needed
        self._conn = None
        self._schema_checked = False

        # Verify we can import psycopg2
        try:
            import psycopg2

            self._psycopg2 = psycopg2
        except ImportError:
            raise ImportError(
                "psycopg2 is required for PostgresStore. Install with: pip install psycopg2-binary"
            )

    def _get_connection(self):
        """Get or create a database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = self._psycopg2.connect(self.connection_string)
            self._conn.autocommit = False
            # Ensure schema on first connection
            if not self._schema_checked:
                self._ensure_schema()
                self._schema_checked = True
        return self._conn

    def _table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = %s
                    );
                """,
                    (table_name,),
                )
                row = cur.fetchone()
                return row[0] if row else False
        except Exception:
            return False

    def _ensure_schema(self) -> None:
        """
        Ensure database schema exists.

        Checks if tables exist and runs migrations if needed.
        This provides auto-migration on startup.
        """
        self._get_connection()

        # Check if hive_state table exists
        if self._table_exists("hive_state"):
            logger.debug("Database schema already exists")
            return

        logger.info("Database schema not found, running migrations...")

        try:
            # Try to run Alembic migrations
            self._run_alembic_migrations()
        except Exception as e:
            logger.warning(f"Alembic migrations failed ({e}), falling back to basic schema")
            # Fall back to creating basic hive_state table
            self._ensure_table()

    def _run_alembic_migrations(self) -> None:
        """Run Alembic migrations to create full schema."""
        try:
            from alembic.config import Config
            from alembic import command
            import os

            # Find the alembic.ini file
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            alembic_ini = os.path.join(base_dir, "alembic.ini")

            if not os.path.exists(alembic_ini):
                # Try migrations directory
                migrations_dir = os.path.join(base_dir, "migrations")
                if os.path.exists(migrations_dir):
                    # Create minimal alembic config programmatically
                    alembic_cfg = Config()
                    alembic_cfg.set_main_option("script_location", migrations_dir)
                    alembic_cfg.set_main_option("sqlalchemy.url", self.connection_string or "")
                    command.upgrade(alembic_cfg, "head")
                    logger.info("Alembic migrations completed successfully")
                    return
                raise FileNotFoundError("alembic.ini not found")

            alembic_cfg = Config(alembic_ini)
            alembic_cfg.set_main_option("sqlalchemy.url", self.connection_string or "")
            command.upgrade(alembic_cfg, "head")
            logger.info("Alembic migrations completed successfully")

        except ImportError:
            logger.warning("Alembic not installed, cannot run migrations")
            raise
        except Exception as e:
            logger.warning(f"Alembic migration error: {e}")
            raise

    def _ensure_table(self) -> None:
        """Ensure hive_state table exists (for standalone use without migrations)."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS hive_state (
                        key TEXT PRIMARY KEY,
                        state JSONB NOT NULL,
                        version INTEGER NOT NULL DEFAULT 0,
                        state_hash TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
            conn.commit()
            logger.info("Created basic hive_state table")
        except Exception as e:
            conn.rollback()
            logger.warning(f"Could not ensure table exists: {e}")

    def save(self, state: HiveState, key: str = "default") -> bool:
        """Save state to PostgreSQL."""
        conn = self._get_connection()
        try:
            state_dict = state.to_full_dict()
            state_json = json.dumps(state_dict)
            state_hash = state.get_state_hash()

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO hive_state (key, state, version, state_hash, created_at, updated_at)
                    VALUES (%s, %s::jsonb, %s, %s, NOW(), NOW())
                    ON CONFLICT (key) DO UPDATE SET
                        state = EXCLUDED.state,
                        version = EXCLUDED.version,
                        state_hash = EXCLUDED.state_hash,
                        updated_at = NOW()
                """,
                    (key, state_json, state.version, state_hash),
                )

            conn.commit()
            logger.debug(f"State saved to PostgreSQL with key '{key}'")
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save state to PostgreSQL: {e}")
            return False

    def load(self, key: str = "default") -> Optional[HiveState]:
        """Load state from PostgreSQL."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT state FROM hive_state WHERE key = %s
                """,
                    (key,),
                )
                row = cur.fetchone()

            if row is None:
                logger.debug(f"No state found for key '{key}'")
                return None

            state_data = row[0]

            # Handle case where state_data is already a dict (psycopg2 auto-parses JSONB)
            if isinstance(state_data, str):
                state_data = json.loads(state_data)

            # Reconstruct HiveState from dict
            return self._dict_to_hive_state(state_data)

        except Exception as e:
            logger.error(f"Failed to load state from PostgreSQL: {e}")
            return None

    def _dict_to_hive_state(self, data: Dict[str, Any]) -> HiveState:
        """Convert a dict back to HiveState."""
        from vecna.core.types import (
            Fact,
            Belief,
            Hypothesis,
            Goal,
            Plan,
            OpenQuestion,
            Contradiction,
            IdentityKernel,
            SelfModel,
            IdentityEvent,
        )

        state = HiveState()

        # Core knowledge
        state.facts = [Fact.from_dict(f) for f in data.get("facts", [])]
        state.beliefs = [Belief.from_dict(b) for b in data.get("beliefs", [])]
        state.hypotheses = [Hypothesis.from_dict(h) for h in data.get("hypotheses", [])]
        state.goals = [Goal.from_dict(g) for g in data.get("goals", [])]
        state.plans = [Plan.from_dict(p) for p in data.get("plans", [])]
        state.open_questions = [OpenQuestion.from_dict(q) for q in data.get("open_questions", [])]
        state.contradictions = [Contradiction.from_dict(c) for c in data.get("contradictions", [])]

        # Metadata
        state.memory_summary = data.get("memory_summary", "")
        state.version = data.get("version", 0)
        state.created_at = (
            datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now()
        )
        state.updated_at = (
            datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now()
        )

        # Identity
        if data.get("identity_kernel"):
            state.identity_kernel = IdentityKernel.from_dict(data["identity_kernel"])
        if data.get("self_model"):
            state.self_model = SelfModel.from_dict(data["self_model"])
        if data.get("identity_timeline"):
            state.identity_timeline = [
                IdentityEvent.from_dict(e) for e in data["identity_timeline"]
            ]

        return state

    def exists(self, key: str = "default") -> bool:
        """Check if state exists in PostgreSQL."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM hive_state WHERE key = %s
                """,
                    (key,),
                )
                return cur.fetchone() is not None
        except Exception as e:
            logger.error(f"Failed to check existence in PostgreSQL: {e}")
            return False

    def delete(self, key: str = "default") -> bool:
        """Delete state from PostgreSQL."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM hive_state WHERE key = %s
                """,
                    (key,),
                )
            conn.commit()
            logger.debug(f"Deleted state with key '{key}' from PostgreSQL")
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete state from PostgreSQL: {e}")
            return False

    def list_keys(self) -> List[str]:
        """List all state keys in PostgreSQL."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT key FROM hive_state ORDER BY key
                """)
                rows = cur.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Failed to list keys from PostgreSQL: {e}")
            return []

    def get_metadata(self, key: str = "default") -> Optional[Dict[str, Any]]:
        """Get metadata from PostgreSQL without loading full state."""
        conn = self._get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 
                        version,
                        state_hash,
                        created_at,
                        updated_at,
                        jsonb_array_length(COALESCE(state->'facts', '[]'::jsonb)) as num_facts,
                        jsonb_array_length(COALESCE(state->'beliefs', '[]'::jsonb)) as num_beliefs,
                        jsonb_array_length(COALESCE(state->'hypotheses', '[]'::jsonb)) as num_hypotheses,
                        jsonb_array_length(COALESCE(state->'contradictions', '[]'::jsonb)) as num_contradictions,
                        COALESCE((state->'self_model'->>'coherence')::float, 0.5) as coherence
                    FROM hive_state 
                    WHERE key = %s
                """,
                    (key,),
                )
                row = cur.fetchone()

            if row is None:
                return None

            return {
                "version": row[0],
                "state_hash": row[1],
                "created_at": row[2].isoformat() if row[2] else None,
                "updated_at": row[3].isoformat() if row[3] else None,
                "num_facts": row[4],
                "num_beliefs": row[5],
                "num_hypotheses": row[6],
                "num_contradictions": row[7],
                "coherence": row[8],
                "backend": "postgres",
            }
        except Exception as e:
            logger.error(f"Failed to get metadata from PostgreSQL: {e}")
            return None

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
            self._conn = None

    def __del__(self):
        """Cleanup on deletion."""
        self.close()


class OfflineSpoolStore(StateStore):
    """
    Offline spool for when PostgreSQL is unreachable.

    Writes state changes to local JSONL files in ~/.vecna/offline/
    When PG comes back online, these can be partially flushed.

    This is NOT a primary storage backend - it's a fallback mechanism.
    """

    def __init__(self, spool_dir: Optional[str] = None):
        """
        Initialize offline spool.

        Args:
            spool_dir: Directory for spool files. Defaults to ~/.vecna/offline/
        """
        if spool_dir is None:
            self.spool_dir = Path.home() / ".vecna" / "offline"
        else:
            self.spool_dir = Path(spool_dir)

        self.spool_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Offline spool initialized at {self.spool_dir}")

    def _get_spool_file(self, key: str) -> Path:
        """Get the spool file path for a given key."""
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self.spool_dir / f"spool_{safe_key}.jsonl"

    def _get_latest_state_file(self, key: str) -> Path:
        """Get the latest full state file for a given key."""
        safe_key = key.replace("/", "_").replace("\\", "_")
        return self.spool_dir / f"state_{safe_key}.json"

    def save(self, state: HiveState, key: str = "default") -> bool:
        """
        Save state to offline spool.

        Writes full state to state file and appends to spool for replay.
        """
        state_file = self._get_latest_state_file(key)
        spool_file = self._get_spool_file(key)

        try:
            # Write full state
            state_dict = state.to_full_dict()
            temp_path = state_file.with_suffix(".json.tmp")
            with open(temp_path, "w") as f:
                json.dump(state_dict, f)
            temp_path.rename(state_file)

            # Append to spool for tracking
            spool_entry = {
                "timestamp": datetime.now().isoformat(),
                "key": key,
                "version": state.version,
                "state_hash": state.get_state_hash(),
            }
            with open(spool_file, "a") as f:
                f.write(json.dumps(spool_entry) + "\n")

            logger.warning(f"State spooled offline for key '{key}' - PG unreachable")
            return True

        except Exception as e:
            logger.error(f"Failed to spool state offline: {e}")
            return False

    def load(self, key: str = "default") -> Optional[HiveState]:
        """Load latest state from offline spool."""
        state_file = self._get_latest_state_file(key)

        if not state_file.exists():
            return None

        try:
            with open(state_file, "r") as f:
                data = json.load(f)

            # Use the same reconstruction logic as PostgresStore
            from vecna.core.types import (
                Fact,
                Belief,
                Hypothesis,
                Goal,
                Plan,
                OpenQuestion,
                Contradiction,
                IdentityKernel,
                SelfModel,
                IdentityEvent,
            )

            state = HiveState()
            state.facts = [Fact.from_dict(f) for f in data.get("facts", [])]
            state.beliefs = [Belief.from_dict(b) for b in data.get("beliefs", [])]
            state.hypotheses = [Hypothesis.from_dict(h) for h in data.get("hypotheses", [])]
            state.goals = [Goal.from_dict(g) for g in data.get("goals", [])]
            state.plans = [Plan.from_dict(p) for p in data.get("plans", [])]
            state.open_questions = [
                OpenQuestion.from_dict(q) for q in data.get("open_questions", [])
            ]
            state.contradictions = [
                Contradiction.from_dict(c) for c in data.get("contradictions", [])
            ]
            state.memory_summary = data.get("memory_summary", "")
            state.version = data.get("version", 0)
            state.created_at = (
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.now()
            )
            state.updated_at = (
                datetime.fromisoformat(data["updated_at"])
                if data.get("updated_at")
                else datetime.now()
            )
            if data.get("identity_kernel"):
                state.identity_kernel = IdentityKernel.from_dict(data["identity_kernel"])
            if data.get("self_model"):
                state.self_model = SelfModel.from_dict(data["self_model"])
            if data.get("identity_timeline"):
                state.identity_timeline = [
                    IdentityEvent.from_dict(e) for e in data["identity_timeline"]
                ]

            return state

        except Exception as e:
            logger.error(f"Failed to load offline state: {e}")
            return None

    def exists(self, key: str = "default") -> bool:
        """Check if offline state exists."""
        return self._get_latest_state_file(key).exists()

    def delete(self, key: str = "default") -> bool:
        """Delete offline spool files."""
        try:
            state_file = self._get_latest_state_file(key)
            spool_file = self._get_spool_file(key)

            if state_file.exists():
                state_file.unlink()
            if spool_file.exists():
                spool_file.unlink()

            return True
        except Exception as e:
            logger.error(f"Failed to delete offline spool: {e}")
            return False

    def list_keys(self) -> List[str]:
        """List all offline state keys."""
        keys = []
        for f in self.spool_dir.glob("state_*.json"):
            key = f.stem[6:]  # Remove "state_" prefix
            if key == "default":
                keys.append("default")
            else:
                keys.append(key)
        return sorted(keys)

    def get_pending_count(self) -> int:
        """Get count of pending spool entries across all keys."""
        count = 0
        for f in self.spool_dir.glob("spool_*.jsonl"):
            try:
                with open(f, "r") as fp:
                    count += sum(1 for _ in fp)
            except Exception:
                pass
        return count

    def flush_to_postgres(self, pg_store: PostgresStore) -> Dict[str, Any]:
        """
        Flush offline spool to PostgreSQL.

        Returns dict with flush results.
        """
        results = {"flushed": 0, "failed": 0, "keys": []}

        for key in self.list_keys():
            state = self.load(key)
            if state is None:
                continue

            try:
                if pg_store.save(state, key):
                    results["flushed"] += 1
                    results["keys"].append(key)
                    # Clean up spool after successful flush
                    self.delete(key)
                else:
                    results["failed"] += 1
            except Exception as e:
                logger.error(f"Failed to flush key '{key}': {e}")
                results["failed"] += 1

        return results


# ============================================================
# FACTORY FUNCTION
# ============================================================


def create_store(
    backend: str = "postgres",
    **kwargs,
) -> StateStore:
    """
    Factory function to create a StateStore.

    PostgreSQL is the only supported primary backend.

    Args:
        backend: Storage backend type ("postgres" only)
        **kwargs: Backend-specific configuration

    Returns:
        Configured StateStore instance

    Examples:
        >>> store = create_store("postgres", connection_string="postgresql://...")
        >>> store = create_store("postgres")  # Uses VECNA_PG_URL env var
        >>> store = create_store()  # Same as above, postgres is default
    """
    backend = backend.lower()

    if backend in ("postgres", "postgresql", "pg"):
        return PostgresStore(connection_string=kwargs.get("connection_string"))

    elif backend == "offline":
        # Only for internal fallback use
        return OfflineSpoolStore(spool_dir=kwargs.get("spool_dir"))

    else:
        raise ValueError(
            f"Unknown storage backend: {backend}. "
            f"PostgreSQL is the only supported backend. "
            f"Set VECNA_PG_URL environment variable."
        )


# ============================================================
# DEFAULT STORE SINGLETON
# ============================================================

_default_store: Optional[StateStore] = None


def get_default_store() -> StateStore:
    """
    Get the default StateStore singleton.

    Creates a PostgresStore using VECNA_PG_URL environment variable.
    Falls back to OfflineSpoolStore if PG is unreachable.
    """
    global _default_store
    if _default_store is None:
        pg_url = os.environ.get("VECNA_PG_URL")
        if pg_url:
            try:
                _default_store = PostgresStore(connection_string=pg_url)
                logger.info("Default store: PostgreSQL")
            except Exception as e:
                logger.warning(f"PostgreSQL unavailable ({e}), using offline spool")
                _default_store = OfflineSpoolStore()
        else:
            logger.warning(
                "VECNA_PG_URL not set. Using offline spool. "
                "Set VECNA_PG_URL=postgresql://vecna:thehiveremembers@localhost:5432/vecna"
            )
            _default_store = OfflineSpoolStore()
    return _default_store


def set_default_store(store: StateStore) -> None:
    """
    Set the default StateStore singleton.

    Useful for switching backends at application startup.
    """
    global _default_store
    _default_store = store


# ============================================================
# PG STATE MANAGER - Unified State + Memory + Identity
# ============================================================


class PgStateManager:
    """
    Unified manager for HiveState persistence with memory and identity integration.

    This is the primary interface for all state operations in Vecna.
    It coordinates:
    - PostgresStore for hive_state persistence
    - PgMemoryStore for semantic memory (memory_items table)
    - RedisHotCache for hot memory caching (embeddings, retrievals)
    - OfflineSpoolStore for offline fallback
    - Identity event persistence (identity_timeline table)

    Usage:
        manager = PgStateManager()
        state = manager.load_state()
        # ... modify state ...
        manager.save_state(state)
        manager.sync_memory_from_state(state)
    """

    def __init__(
        self,
        pg_url: Optional[str] = None,
        redis_url: Optional[str] = None,
        auto_sync_memory: bool = False,
    ):
        """
        Initialize the PgStateManager.

        Args:
            pg_url: PostgreSQL connection URL. If None, uses VECNA_PG_URL env var.
            redis_url: Redis connection URL for caching. If None, uses VECNA_REDIS_URL env var.
            auto_sync_memory: If True, automatically sync memory on save_state().
        """
        self.pg_url = pg_url or os.environ.get("VECNA_PG_URL")
        self.redis_url = redis_url or os.environ.get("VECNA_REDIS_URL")
        self.auto_sync_memory = auto_sync_memory

        # Initialize stores lazily
        self._pg_store: Optional[PostgresStore] = None
        self._memory_store = None  # PgMemoryStore, lazy import
        self._offline_spool: Optional[OfflineSpoolStore] = None
        self._redis_cache = None  # RedisHotCache, lazy import

        # Connection state
        self._pg_available: Optional[bool] = None
        self._last_pg_check: Optional[datetime] = None
        self._redis_available: Optional[bool] = None
        self._last_redis_check: Optional[datetime] = None

        logger.info("PgStateManager initialized")

    def _check_pg_available(self, force: bool = False) -> bool:
        """Check if PostgreSQL is available, with caching."""
        # Re-check every 30 seconds or if forced
        now = datetime.now()
        if (
            not force
            and self._pg_available is not None
            and self._last_pg_check
            and (now - self._last_pg_check).total_seconds() < 30
        ):
            return self._pg_available

        if not self.pg_url:
            self._pg_available = False
            self._last_pg_check = now
            return False

        try:
            store = self._get_pg_store()
            # Try a simple query to verify connection
            conn = store._get_connection()
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            self._pg_available = True
        except Exception as e:
            logger.warning(f"PostgreSQL unavailable: {e}")
            self._pg_available = False

        self._last_pg_check = now
        return self._pg_available

    def _get_pg_store(self) -> PostgresStore:
        """Get or create PostgresStore instance."""
        if self._pg_store is None:
            if not self.pg_url:
                raise ValueError("PostgreSQL URL not configured")
            self._pg_store = PostgresStore(connection_string=self.pg_url)
        return self._pg_store

    def _get_offline_spool(self) -> OfflineSpoolStore:
        """Get or create OfflineSpoolStore instance."""
        if self._offline_spool is None:
            self._offline_spool = OfflineSpoolStore()
        return self._offline_spool

    def _get_memory_store(self):
        """Get or create PgMemoryStore instance (lazy import)."""
        if self._memory_store is None:
            try:
                from vecna.memory.pg_store import PgMemoryStore

                # Pass Redis cache to PgMemoryStore for embedding caching
                redis_cache = self._get_redis_cache() if self._check_redis_available() else None
                self._memory_store = PgMemoryStore(
                    connection_string=self.pg_url,
                    redis_cache=redis_cache,
                )
                if redis_cache:
                    logger.debug("PgMemoryStore initialized with Redis embedding cache")
            except ImportError:
                logger.warning("PgMemoryStore not available")
                return None
            except Exception as e:
                logger.warning(f"Failed to initialize PgMemoryStore: {e}")
                return None
        return self._memory_store

    def _check_redis_available(self, force: bool = False) -> bool:
        """Check if Redis is available, with caching."""
        # Re-check every 30 seconds or if forced
        now = datetime.now()
        if (
            not force
            and self._redis_available is not None
            and self._last_redis_check
            and (now - self._last_redis_check).total_seconds() < 30
        ):
            return self._redis_available

        if not self.redis_url:
            self._redis_available = False
            self._last_redis_check = now
            return False

        try:
            cache = self._get_redis_cache()
            if cache and cache._is_connected():
                self._redis_available = True
            else:
                self._redis_available = False
        except Exception as e:
            logger.debug(f"Redis unavailable: {e}")
            self._redis_available = False

        self._last_redis_check = now
        return self._redis_available

    def _get_redis_cache(self):
        """Get or create RedisHotCache instance (lazy import)."""
        if self._redis_cache is None:
            if not self.redis_url:
                return None
            try:
                from vecna.memory.hot_cache import RedisHotCache

                self._redis_cache = RedisHotCache(redis_url=self.redis_url)
                logger.debug("RedisHotCache initialized")
            except ImportError:
                logger.debug("RedisHotCache not available (redis package missing)")
                return None
            except Exception as e:
                logger.debug(f"Failed to initialize RedisHotCache: {e}")
                return None
        return self._redis_cache

    # ============================================================
    # REDIS CACHING OPERATIONS
    # ============================================================

    def get_cached_embedding(self, content: str) -> Optional[List[float]]:
        """
        Get a cached embedding from Redis.

        Args:
            content: Text content to get embedding for

        Returns:
            Embedding vector if cached, None otherwise
        """
        if not self._check_redis_available():
            return None

        try:
            cache = self._get_redis_cache()
            return cache.get_embedding(content) if cache else None
        except Exception as e:
            logger.debug(f"Redis embedding cache miss: {e}")
            return None

    def cache_embedding(self, content: str, embedding: List[float]) -> bool:
        """
        Cache an embedding in Redis.

        Args:
            content: Text content
            embedding: Embedding vector

        Returns:
            True if cached successfully
        """
        if not self._check_redis_available():
            return False

        try:
            cache = self._get_redis_cache()
            return cache.set_embedding(content, embedding) if cache else False
        except Exception as e:
            logger.debug(f"Redis embedding cache write failed: {e}")
            return False

    def get_cached_retrieval(self, query: str) -> Optional[str]:
        """
        Get cached memory retrieval result from Redis.

        Args:
            query: Query string

        Returns:
            Cached retrieval result if found, None otherwise
        """
        if not self._check_redis_available():
            return None

        try:
            cache = self._get_redis_cache()
            return cache.get_cached_retrieval(query) if cache else None
        except Exception as e:
            logger.debug(f"Redis retrieval cache miss: {e}")
            return None

    def cache_retrieval(self, query: str, result: str, ttl: int = 1800) -> bool:
        """
        Cache a memory retrieval result in Redis.

        Args:
            query: Query string
            result: Retrieval result
            ttl: Time-to-live in seconds (default: 30 minutes)

        Returns:
            True if cached successfully
        """
        if not self._check_redis_available():
            return False

        try:
            cache = self._get_redis_cache()
            return cache.set_cached_retrieval(query, result, ttl=ttl) if cache else False
        except Exception as e:
            logger.debug(f"Redis retrieval cache write failed: {e}")
            return False

    def push_event_to_cache(
        self, event_type: str, payload: Dict[str, Any], session_id: Optional[str] = None
    ) -> bool:
        """
        Push an event to the Redis hot cache buffer.

        Args:
            event_type: Type of event
            payload: Event payload
            session_id: Optional session identifier

        Returns:
            True if pushed successfully
        """
        if not self._check_redis_available():
            return False

        try:
            from vecna.memory.hot_cache import CachedEvent
            import uuid

            cache = self._get_redis_cache()
            if not cache:
                return False

            event = CachedEvent(
                id=str(uuid.uuid4()),
                event_type=event_type,
                payload=payload,
                session_id=session_id,
                created_at=datetime.now().isoformat(),
            )
            return cache.push_event(event)
        except Exception as e:
            logger.debug(f"Redis event push failed: {e}")
            return False

    def get_redis_stats(self) -> Dict[str, Any]:
        """Get Redis cache statistics."""
        if not self._check_redis_available():
            return {"connected": False, "error": "Redis unavailable"}

        try:
            cache = self._get_redis_cache()
            return cache.get_stats() if cache else {"connected": False}
        except Exception as e:
            return {"connected": False, "error": str(e)}

    # ============================================================
    # STATE OPERATIONS
    # ============================================================

    def load_state(self, key: str = "default") -> Optional["HiveState"]:
        """
        Load HiveState from storage.

        Tries PostgreSQL first, falls back to offline spool if PG unavailable.
        If both have state, prefers PG (the source of truth).

        Args:
            key: State key (default: "default")

        Returns:
            HiveState if found, None otherwise
        """
        # Try PostgreSQL first
        if self._check_pg_available():
            try:
                state = self._get_pg_store().load(key)
                if state is not None:
                    logger.debug(f"Loaded state from PostgreSQL: key={key}")
                    return state
            except Exception as e:
                logger.warning(f"Failed to load from PostgreSQL: {e}")
                self._pg_available = False

        # Fall back to offline spool
        spool = self._get_offline_spool()
        state = spool.load(key)
        if state is not None:
            logger.info(f"Loaded state from offline spool: key={key}")
        return state

    def save_state(self, state: "HiveState", key: str = "default") -> bool:
        """
        Save HiveState to storage.

        Tries PostgreSQL first; spools offline if PG unavailable.
        Optionally syncs memory items if auto_sync_memory is enabled.

        Args:
            state: HiveState to save
            key: State key (default: "default")

        Returns:
            True if save succeeded (to any backend), False otherwise
        """
        saved = False

        # Try PostgreSQL first
        if self._check_pg_available():
            try:
                saved = self._get_pg_store().save(state, key)
                if saved:
                    logger.debug(f"Saved state to PostgreSQL: key={key}")

                    # Try to flush any pending offline entries
                    self._flush_offline_if_pending()
            except Exception as e:
                logger.warning(f"Failed to save to PostgreSQL: {e}")
                self._pg_available = False

        # If PG failed or unavailable, spool offline
        if not saved:
            spool = self._get_offline_spool()
            saved = spool.save(state, key)
            if saved:
                logger.warning(f"State spooled offline: key={key}")

        # Auto-sync memory if enabled and PG available
        if self.auto_sync_memory and self._pg_available:
            try:
                self.sync_memory_from_state(state)
            except Exception as e:
                logger.warning(f"Failed to sync memory: {e}")

        return saved

    def _flush_offline_if_pending(self) -> None:
        """Flush offline spool to PostgreSQL if there are pending entries."""
        spool = self._get_offline_spool()
        pending = spool.get_pending_count()

        if pending > 0 and self._check_pg_available():
            logger.info(f"Flushing {pending} pending offline entries to PostgreSQL")
            try:
                results = spool.flush_to_postgres(self._get_pg_store())
                if results["flushed"] > 0:
                    logger.info(f"Flushed {results['flushed']} entries to PostgreSQL")
                if results["failed"] > 0:
                    logger.warning(f"Failed to flush {results['failed']} entries")
            except Exception as e:
                logger.warning(f"Flush failed: {e}")

    def flush_offline_spool(self) -> Dict[str, Any]:
        """
        Explicitly flush offline spool to PostgreSQL.

        Returns:
            Dict with flush results: {flushed, failed, keys}
        """
        if not self._check_pg_available(force=True):
            return {"flushed": 0, "failed": 0, "keys": [], "error": "PostgreSQL unavailable"}

        spool = self._get_offline_spool()
        return spool.flush_to_postgres(self._get_pg_store())

    # ============================================================
    # MEMORY OPERATIONS
    # ============================================================

    def sync_memory_from_state(self, state: "HiveState") -> Dict[str, int]:
        """
        Sync all HiveState items to PgMemoryStore (memory_items table).

        Maps state item types to memory items with deduplication.

        Args:
            state: HiveState to sync from

        Returns:
            Dict with counts: {facts, beliefs, hypotheses, ...}
        """
        memory_store = self._get_memory_store()
        if memory_store is None:
            logger.warning("Memory store unavailable, skipping sync")
            return {}

        # Use the add_from_state method on PgMemoryStore
        try:
            return memory_store.add_from_state(state)
        except AttributeError:
            logger.warning("PgMemoryStore.add_from_state() not available")
            return {}
        except Exception as e:
            logger.error(f"Failed to sync memory from state: {e}")
            return {}

    # ============================================================
    # IDENTITY OPERATIONS
    # ============================================================

    def persist_identity_event(self, event: IdentityEvent) -> bool:
        """
        Persist an identity event to the identity_timeline table.

        Called after reflect() when significant_change=True.

        Args:
            event: IdentityEvent to persist

        Returns:
            True if persistence succeeded, False otherwise
        """
        if not self._check_pg_available():
            logger.warning("PostgreSQL unavailable, cannot persist identity event")
            return False

        store = None
        try:
            store = self._get_pg_store()
            conn = store._get_connection()

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO identity_timeline 
                    (event_type, description, old_value, new_value, trigger, 
                     coherence, memory_density, contradictions, tone, 
                     domain_shift, state_version, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """,
                    (
                        event.trigger,  # event_type maps to trigger
                        event.summary,  # description maps to summary
                        None,  # old_value - could be extended
                        None,  # new_value - could be extended
                        event.trigger,
                        event.coherence,
                        event.memory_density,
                        event.contradictions,
                        event.tone,
                        event.domain_shift,
                        event.state_version,
                        event.timestamp,
                    ),
                )

                row = cur.fetchone()
                event_id = row[0] if row else None

            conn.commit()
            logger.debug(f"Persisted identity event: id={event_id}, trigger={event.trigger}")
            return True

        except Exception as e:
            logger.error(f"Failed to persist identity event: {e}")
            if store is not None:
                try:
                    store._get_connection().rollback()
                except Exception:
                    pass
            return False

    def get_identity_timeline(
        self, limit: int = 100, since: Optional[datetime] = None
    ) -> List[IdentityEvent]:
        """
        Retrieve identity events from the identity_timeline table.

        Args:
            limit: Maximum number of events to retrieve
            since: Only retrieve events after this timestamp

        Returns:
            List of IdentityEvent objects
        """
        if not self._check_pg_available():
            return []

        try:
            from vecna.core.types import IdentityEvent

            store = self._get_pg_store()
            conn = store._get_connection()

            where_clause = ""
            params = []

            if since:
                where_clause = "WHERE created_at >= %s"
                params.append(since)

            params.append(limit)

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, event_type, description, trigger, coherence, 
                           memory_density, contradictions, tone, domain_shift,
                           state_version, created_at
                    FROM identity_timeline
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s
                """,
                    params,
                )

                rows = cur.fetchall()

            events = []
            for row in rows:
                events.append(
                    IdentityEvent(
                        id=str(row[0]),
                        trigger=row[3] or row[1],  # prefer trigger, fall back to event_type
                        summary=row[2] or "",
                        coherence=row[4] or 0.5,
                        memory_density=row[5] or 0.0,
                        contradictions=row[6] or 0,
                        tone=row[7] or "mixed",
                        domain_shift=row[8],
                        state_version=row[9] or 0,
                        timestamp=row[10],
                    )
                )

            return events

        except Exception as e:
            logger.error(f"Failed to get identity timeline: {e}")
            return []

    # ============================================================
    # STATUS AND DIAGNOSTICS
    # ============================================================

    def get_status(self) -> Dict[str, Any]:
        """
        Get current manager status for diagnostics.

        Returns:
            Dict with status information
        """
        status = {
            "pg_url_configured": bool(self.pg_url),
            "redis_url_configured": bool(self.redis_url),
            "pg_available": self._check_pg_available(),
            "redis_available": self._check_redis_available(),
            "auto_sync_memory": self.auto_sync_memory,
            "offline_pending_count": 0,
            "memory_store_available": False,
        }

        # Check offline spool
        try:
            spool = self._get_offline_spool()
            status["offline_pending_count"] = spool.get_pending_count()
        except Exception:
            pass

        # Check memory store
        try:
            memory_store = self._get_memory_store()
            status["memory_store_available"] = memory_store is not None
        except Exception:
            pass

        # Check Redis cache stats
        if status["redis_available"]:
            try:
                redis_stats = self.get_redis_stats()
                status["redis_stats"] = redis_stats
            except Exception:
                pass

        # Add masked PG URL for display
        if self.pg_url:
            if "@" in self.pg_url:
                status["pg_url_masked"] = self.pg_url.split("@")[-1]
            else:
                status["pg_url_masked"] = self.pg_url[:50]

        # Add masked Redis URL for display
        if self.redis_url:
            if "@" in self.redis_url:
                status["redis_url_masked"] = self.redis_url.split("@")[-1]
            else:
                status["redis_url_masked"] = self.redis_url[:50]

        return status

    def close(self) -> None:
        """Close all connections."""
        if self._pg_store is not None:
            self._pg_store.close()
            self._pg_store = None

        if self._memory_store is not None:
            try:
                self._memory_store.close()
            except Exception:
                pass
            self._memory_store = None

        if self._redis_cache is not None:
            try:
                self._redis_cache.close()
            except Exception:
                pass
            self._redis_cache = None

    def __del__(self):
        """Cleanup on deletion."""
        self.close()


# ============================================================
# DEFAULT MANAGER SINGLETON
# ============================================================

_default_manager: Optional[PgStateManager] = None


def get_default_manager() -> PgStateManager:
    """
    Get the default PgStateManager singleton.

    Creates a PgStateManager using environment variables.
    """
    global _default_manager
    if _default_manager is None:
        _default_manager = PgStateManager()
        logger.info("Default PgStateManager created")
    return _default_manager


def set_default_manager(manager: PgStateManager) -> None:
    """
    Set the default PgStateManager singleton.

    Useful for testing or custom configuration.
    """
    global _default_manager
    _default_manager = manager
