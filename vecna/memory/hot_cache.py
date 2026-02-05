"""
Redis Hot Cache for Vecna Memory Substrate.

This module provides:
- Fast in-memory cache for recent events and context
- Shared hot memory for multi-process Vecna
- Write-through caching to PostgreSQL
- Embedding cache to reduce OpenAI API costs
- Distributed locks for multi-process coordination

The hot cache is the fastest tier in the memory substrate.
"""

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import json
import hashlib
import os
import logging
import threading
from contextlib import contextmanager

logger = logging.getLogger("vecna.memory.hot_cache")


@dataclass
class CachedEvent:
    """A cached event in the hot memory."""

    id: str
    event_type: str
    payload: Dict[str, Any]
    session_id: Optional[str]
    created_at: str  # ISO format

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CachedEvent":
        return cls(**data)


class RedisHotCache:
    """
    Redis-based hot memory cache for Vecna.

    Provides:
    - Recent events buffer (ring buffer)
    - Current context cache
    - Embedding cache (cost savings)
    - Retrieval cache (LRU)
    - Distributed locks
    """

    # Key prefixes
    PREFIX = "vecna:"
    EVENTS_KEY = "vecna:events:recent"
    CONTEXT_KEY = "vecna:context:current"
    GOALS_KEY = "vecna:goals:active"
    EMBED_PREFIX = "vecna:embed:"
    MEMORY_CACHE_PREFIX = "vecna:memory:cache:"
    LOCK_PREFIX = "vecna:lock:"

    # Default TTLs (seconds)
    DEFAULT_EVENT_TTL = 3600  # 1 hour
    DEFAULT_CONTEXT_TTL = 600  # 10 minutes
    DEFAULT_GOALS_TTL = 300  # 5 minutes
    DEFAULT_EMBED_TTL = 86400  # 24 hours
    DEFAULT_MEMORY_TTL = 1800  # 30 minutes
    DEFAULT_LOCK_TTL = 30  # 30 seconds

    # Buffer sizes
    MAX_RECENT_EVENTS = 1000

    def __init__(
        self,
        redis_url: Optional[str] = None,
        max_events: int = MAX_RECENT_EVENTS,
        event_ttl: int = DEFAULT_EVENT_TTL,
        embed_ttl: int = DEFAULT_EMBED_TTL,
    ):
        """
        Initialize the Redis hot cache.

        Args:
            redis_url: Redis connection URL.
                If None, reads from VECNA_REDIS_URL environment variable.
            max_events: Maximum number of recent events to keep.
            event_ttl: TTL for event buffer in seconds.
            embed_ttl: TTL for embedding cache in seconds.
        """
        self.redis_url = redis_url or os.environ.get("VECNA_REDIS_URL")
        if not self.redis_url:
            raise ValueError(
                "RedisHotCache requires a Redis URL. "
                "Pass it directly or set VECNA_REDIS_URL environment variable."
            )

        self.max_events = max_events
        self.event_ttl = event_ttl
        self.embed_ttl = embed_ttl

        # Lazy initialization
        self._redis = None
        self._redis_module = None

        # Local fallback cache (in-memory)
        self._local_cache: Dict[str, Any] = {}
        self._local_lock = threading.Lock()

        # Import redis
        try:
            import redis

            self._redis_module = redis
        except ImportError:
            raise ImportError(
                "redis package is required for RedisHotCache. Install with: pip install redis"
            )

    def _get_redis(self):
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = self._redis_module.from_url(self.redis_url, decode_responses=True)
        return self._redis

    def _is_connected(self) -> bool:
        """Check if Redis is connected."""
        try:
            self._get_redis().ping()
            return True
        except Exception:
            return False

    # ============================================================
    # EVENT BUFFER (Ring Buffer)
    # ============================================================

    def push_event(self, event: CachedEvent) -> bool:
        """
        Push an event to the recent events buffer.

        Uses a Redis list as a ring buffer with LPUSH + LTRIM.
        """
        try:
            r = self._get_redis()
            # Handle both dataclass objects and dicts
            if hasattr(event, "__dataclass_fields__"):
                event_dict = asdict(event)
                # Convert datetime to ISO string for JSON serialization (if needed)
                if "created_at" in event_dict and event_dict["created_at"]:
                    if hasattr(event_dict["created_at"], "isoformat"):
                        event_dict["created_at"] = event_dict["created_at"].isoformat()
                    # else: already a string, keep as is
            else:
                event_dict = event if isinstance(event, dict) else event.to_dict()
            event_json = json.dumps(event_dict, default=str)

            pipe = r.pipeline()
            pipe.lpush(self.EVENTS_KEY, event_json)
            pipe.ltrim(self.EVENTS_KEY, 0, self.max_events - 1)
            pipe.expire(self.EVENTS_KEY, self.event_ttl)
            pipe.execute()

            return True

        except Exception as e:
            logger.warning(f"Failed to push event to Redis: {e}")
            # Fallback to local cache
            with self._local_lock:
                if "events" not in self._local_cache:
                    self._local_cache["events"] = []
                # Handle both dataclass objects and dicts
                if hasattr(event, "__dataclass_fields__"):
                    event_dict = asdict(event)
                    if "created_at" in event_dict and event_dict["created_at"]:
                        if hasattr(event_dict["created_at"], "isoformat"):
                            event_dict["created_at"] = event_dict["created_at"].isoformat()
                        # else: already a string, keep as is
                else:
                    event_dict = event if isinstance(event, dict) else event.to_dict()
                self._local_cache["events"].insert(0, event_dict)
                self._local_cache["events"] = self._local_cache["events"][: self.max_events]
            return True

    def get_recent_events(
        self, limit: int = 100, event_type: Optional[str] = None
    ) -> List[CachedEvent]:
        """
        Get recent events from the buffer.

        Args:
            limit: Maximum number of events to return.
            event_type: Filter by event type (optional).
        """
        try:
            r = self._get_redis()
            raw_events = r.lrange(self.EVENTS_KEY, 0, limit - 1)

            events = []
            for raw in raw_events:
                try:
                    data = json.loads(raw)
                    event = CachedEvent.from_dict(data)
                    if event_type is None or event.event_type == event_type:
                        events.append(event)
                except Exception:
                    continue

            return events

        except Exception as e:
            logger.warning(f"Failed to get events from Redis: {e}")
            # Fallback to local cache
            with self._local_lock:
                local_events = self._local_cache.get("events", [])[:limit]
                events = []
                for data in local_events:
                    event = CachedEvent.from_dict(data)
                    if event_type is None or event.event_type == event_type:
                        events.append(event)
                return events

    def clear_events(self) -> bool:
        """Clear the event buffer."""
        try:
            r = self._get_redis()
            r.delete(self.EVENTS_KEY)
            return True
        except Exception as e:
            logger.warning(f"Failed to clear events in Redis: {e}")
            with self._local_lock:
                self._local_cache["events"] = []
            return True

    # ============================================================
    # CONTEXT CACHE
    # ============================================================

    def set_context(self, context: Dict[str, Any], ttl: Optional[int] = None) -> bool:
        """
        Set the current task context.

        This is the "working memory" for the current task.
        """
        ttl = ttl or self.DEFAULT_CONTEXT_TTL

        try:
            r = self._get_redis()
            r.setex(self.CONTEXT_KEY, ttl, json.dumps(context))
            return True
        except Exception as e:
            logger.warning(f"Failed to set context in Redis: {e}")
            with self._local_lock:
                self._local_cache["context"] = context
            return True

    def get_context(self) -> Optional[Dict[str, Any]]:
        """Get the current task context."""
        try:
            r = self._get_redis()
            raw = r.get(self.CONTEXT_KEY)
            if raw:
                return json.loads(raw)
            return None
        except Exception as e:
            logger.warning(f"Failed to get context from Redis: {e}")
            with self._local_lock:
                return self._local_cache.get("context")

    def update_context(self, updates: Dict[str, Any]) -> bool:
        """Update specific fields in the current context."""
        context = self.get_context() or {}
        context.update(updates)
        return self.set_context(context)

    # ============================================================
    # GOALS CACHE
    # ============================================================

    def set_active_goals(self, goals: List[Dict[str, Any]], ttl: Optional[int] = None) -> bool:
        """Set the active goals."""
        ttl = ttl or self.DEFAULT_GOALS_TTL

        try:
            r = self._get_redis()
            r.setex(self.GOALS_KEY, ttl, json.dumps(goals))
            return True
        except Exception as e:
            logger.warning(f"Failed to set goals in Redis: {e}")
            with self._local_lock:
                self._local_cache["goals"] = goals
            return True

    def get_active_goals(self) -> List[Dict[str, Any]]:
        """Get the active goals."""
        try:
            r = self._get_redis()
            raw = r.get(self.GOALS_KEY)
            if raw:
                return json.loads(raw)
            return []
        except Exception as e:
            logger.warning(f"Failed to get goals from Redis: {e}")
            with self._local_lock:
                return self._local_cache.get("goals", [])

    # ============================================================
    # EMBEDDING CACHE
    # ============================================================

    def _embed_key(self, content: str) -> str:
        """Generate cache key for embedding."""
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:32]
        return f"{self.EMBED_PREFIX}{content_hash}"

    def get_embedding(self, content: str) -> Optional[List[float]]:
        """
        Get cached embedding for content.

        Returns None if not cached.
        """
        key = self._embed_key(content)

        try:
            r = self._get_redis()
            raw = r.get(key)
            if raw:
                return json.loads(raw)
            return None
        except Exception as e:
            logger.warning(f"Failed to get embedding from Redis: {e}")
            with self._local_lock:
                return self._local_cache.get(key)

    def set_embedding(
        self, content: str, embedding: List[float], ttl: Optional[int] = None
    ) -> bool:
        """Cache an embedding."""
        key = self._embed_key(content)
        ttl = ttl or self.embed_ttl

        try:
            r = self._get_redis()
            r.setex(key, ttl, json.dumps(embedding))
            return True
        except Exception as e:
            logger.warning(f"Failed to set embedding in Redis: {e}")
            with self._local_lock:
                self._local_cache[key] = embedding
            return True

    def get_embeddings_batch(self, contents: List[str]) -> Dict[str, Optional[List[float]]]:
        """
        Get cached embeddings for multiple contents.

        Returns dict mapping content to embedding (or None if not cached).
        """
        if not contents:
            return {}

        keys = [self._embed_key(c) for c in contents]

        try:
            r = self._get_redis()
            values = r.mget(keys)

            result = {}
            for content, raw in zip(contents, values):
                if raw:
                    result[content] = json.loads(raw)
                else:
                    result[content] = None

            return result

        except Exception as e:
            logger.warning(f"Failed to get embeddings batch from Redis: {e}")
            result = {}
            with self._local_lock:
                for content in contents:
                    key = self._embed_key(content)
                    result[content] = self._local_cache.get(key)
            return result

    def set_embeddings_batch(
        self, embeddings: Dict[str, List[float]], ttl: Optional[int] = None
    ) -> bool:
        """Cache multiple embeddings at once."""
        if not embeddings:
            return True

        ttl = ttl or self.embed_ttl

        try:
            r = self._get_redis()
            pipe = r.pipeline()

            for content, embedding in embeddings.items():
                key = self._embed_key(content)
                pipe.setex(key, ttl, json.dumps(embedding))

            pipe.execute()
            return True

        except Exception as e:
            logger.warning(f"Failed to set embeddings batch in Redis: {e}")
            with self._local_lock:
                for content, embedding in embeddings.items():
                    key = self._embed_key(content)
                    self._local_cache[key] = embedding
            return True

    # ============================================================
    # MEMORY RETRIEVAL CACHE
    # ============================================================

    def _memory_cache_key(self, query: str) -> str:
        """Generate cache key for memory retrieval."""
        query_hash = hashlib.sha256(query.encode()).hexdigest()[:32]
        return f"{self.MEMORY_CACHE_PREFIX}{query_hash}"

    def get_cached_retrieval(self, query: str) -> Optional[str]:
        """Get cached retrieval result for a query."""
        key = self._memory_cache_key(query)

        try:
            r = self._get_redis()
            return r.get(key)
        except Exception as e:
            logger.warning(f"Failed to get cached retrieval from Redis: {e}")
            with self._local_lock:
                return self._local_cache.get(key)

    def set_cached_retrieval(self, query: str, result: str, ttl: Optional[int] = None) -> bool:
        """Cache a retrieval result."""
        key = self._memory_cache_key(query)
        ttl = ttl or self.DEFAULT_MEMORY_TTL

        try:
            r = self._get_redis()
            r.setex(key, ttl, result)
            return True
        except Exception as e:
            logger.warning(f"Failed to set cached retrieval in Redis: {e}")
            with self._local_lock:
                self._local_cache[key] = result
            return True

    # ============================================================
    # DISTRIBUTED LOCKS
    # ============================================================

    @contextmanager
    def lock(
        self, resource: str, ttl: Optional[int] = None, blocking: bool = True, timeout: float = 10.0
    ):
        """
        Acquire a distributed lock.

        Usage:
            with cache.lock("memory_write"):
                # Critical section
                pass

        Args:
            resource: Name of the resource to lock.
            ttl: Lock TTL in seconds.
            blocking: Whether to wait for the lock.
            timeout: How long to wait for the lock.
        """
        ttl = ttl or self.DEFAULT_LOCK_TTL
        key = f"{self.LOCK_PREFIX}{resource}"
        lock_id = hashlib.sha256(os.urandom(16)).hexdigest()[:16]

        acquired = False

        try:
            r = self._get_redis()

            if blocking:
                start = datetime.now()
                while (datetime.now() - start).total_seconds() < timeout:
                    acquired = r.set(key, lock_id, nx=True, ex=ttl)
                    if acquired:
                        break
                    import time

                    time.sleep(0.1)
            else:
                acquired = r.set(key, lock_id, nx=True, ex=ttl)

            if not acquired:
                raise TimeoutError(f"Could not acquire lock for {resource}")

            yield acquired

        except Exception as e:
            if "Could not acquire lock" not in str(e):
                logger.warning(f"Lock error for {resource}: {e}")
            raise

        finally:
            if acquired:
                try:
                    # Only release if we still own the lock
                    r = self._get_redis()
                    if r.get(key) == lock_id:
                        r.delete(key)
                except Exception:
                    pass

    def is_locked(self, resource: str) -> bool:
        """Check if a resource is locked."""
        key = f"{self.LOCK_PREFIX}{resource}"

        try:
            r = self._get_redis()
            return r.exists(key) > 0
        except Exception:
            return False

    # ============================================================
    # STATS AND MANAGEMENT
    # ============================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        try:
            r = self._get_redis()

            stats = {
                "connected": True,
                "event_count": r.llen(self.EVENTS_KEY),
                "has_context": r.exists(self.CONTEXT_KEY) > 0,
                "has_goals": r.exists(self.GOALS_KEY) > 0,
            }

            # Count embedding cache entries
            embed_keys = r.keys(f"{self.EMBED_PREFIX}*")
            stats["cached_embeddings"] = len(embed_keys)

            # Count memory cache entries
            memory_keys = r.keys(f"{self.MEMORY_CACHE_PREFIX}*")
            stats["cached_retrievals"] = len(memory_keys)

            # Redis info
            info = r.info("memory")
            stats["redis_memory_used"] = info.get("used_memory_human", "unknown")

            return stats

        except Exception as e:
            logger.warning(f"Failed to get Redis stats: {e}")
            return {"connected": False, "error": str(e), "local_cache_size": len(self._local_cache)}

    def clear_all(self) -> bool:
        """Clear all Vecna-related keys from Redis."""
        try:
            r = self._get_redis()

            # Find and delete all vecna: keys
            keys = r.keys(f"{self.PREFIX}*")
            if keys:
                r.delete(*keys)

            # Clear local cache too
            with self._local_lock:
                self._local_cache.clear()

            return True

        except Exception as e:
            logger.error(f"Failed to clear Redis cache: {e}")
            return False

    def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            self._redis.close()
            self._redis = None

    def __del__(self):
        """Cleanup on deletion."""
        self.close()


class HotMemoryManager:
    """
    High-level manager combining Redis hot cache with PG warm storage.

    Provides write-through caching and coordinated retrieval.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        pg_url: Optional[str] = None,
    ):
        """
        Initialize the hot memory manager.

        Args:
            redis_url: Redis connection URL (or VECNA_REDIS_URL env var).
            pg_url: PostgreSQL connection URL (or VECNA_PG_URL env var).
        """
        self.hot_cache = RedisHotCache(redis_url=redis_url)

        # Lazy init for PG store
        self._pg_store = None
        self._pg_url = pg_url

    def _get_pg_store(self):
        """Lazy initialization of PG memory store."""
        if self._pg_store is None:
            from vecna.memory.pg_store import PgMemoryStore

            self._pg_store = PgMemoryStore(connection_string=self._pg_url)
        return self._pg_store

    def push_event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        session_id: Optional[str] = None,
        persist: bool = True,
    ) -> Optional[str]:
        """
        Push an event to hot cache and optionally persist to PG.

        Args:
            event_type: Type of event.
            payload: Event payload.
            session_id: Session identifier.
            persist: Whether to also write to PostgreSQL.

        Returns:
            Event ID if persisted, None otherwise.
        """
        import uuid

        event_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        cached_event = CachedEvent(
            id=event_id,
            event_type=event_type,
            payload=payload,
            session_id=session_id,
            created_at=now,
        )

        # Always push to hot cache
        self.hot_cache.push_event(cached_event)

        # Optionally persist to PG
        if persist:
            try:
                from vecna.memory.pg_store import MemoryEvent

                pg_store = self._get_pg_store()
                pg_event = MemoryEvent(
                    event_type=event_type, payload=payload, session_id=session_id
                )
                pg_store.add_event(pg_event)
            except Exception as e:
                logger.warning(f"Failed to persist event to PG: {e}")

        return event_id

    def get_embedding_cached(self, content: str) -> Optional[List[float]]:
        """
        Get embedding with caching.

        Checks hot cache first, then generates if not found.
        """
        # Check hot cache
        cached = self.hot_cache.get_embedding(content)
        if cached is not None:
            return cached

        # Generate and cache
        try:
            pg_store = self._get_pg_store()
            embeddings = pg_store.embed([content])
            if len(embeddings) > 0:
                embedding = embeddings[0].tolist()
                self.hot_cache.set_embedding(content, embedding)
                return embedding
        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")

        return None

    def retrieve_with_cache(
        self, query: str, max_items: int = 15, max_chars: int = 3000, cache_ttl: int = 1800
    ) -> str:
        """
        Retrieve memory with caching.

        Checks hot cache first, then queries PG if not found.
        """
        # Check hot cache
        cached = self.hot_cache.get_cached_retrieval(query)
        if cached is not None:
            return cached

        # Query PG
        try:
            pg_store = self._get_pg_store()
            result = pg_store.get_relevant_context(query, max_items=max_items, max_chars=max_chars)

            # Cache result
            self.hot_cache.set_cached_retrieval(query, result, ttl=cache_ttl)

            return result

        except Exception as e:
            logger.error(f"Failed to retrieve from PG: {e}")
            return "Memory retrieval failed."

    def get_stats(self) -> Dict[str, Any]:
        """Get combined stats from hot and warm memory."""
        stats = {"hot_cache": self.hot_cache.get_stats()}

        try:
            pg_store = self._get_pg_store()
            stats["warm_storage"] = pg_store.get_stats()
        except Exception as e:
            stats["warm_storage"] = {"error": str(e)}

        return stats

    def close(self) -> None:
        """Close all connections."""
        self.hot_cache.close()
        if self._pg_store is not None:
            self._pg_store.close()
