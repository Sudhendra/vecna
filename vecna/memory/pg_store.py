"""
PostgreSQL Memory Store with pgvector support.

This module provides:
- Vector-based semantic memory using pgvector
- Memory graph operations (edges/relations)
- Episodic event storage
- RLM-style retrieval pipeline

Designed for the Vecna hive mind substrate.
"""

from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
import hashlib
import os
import logging

import numpy as np

logger = logging.getLogger("vecna.memory.pg_store")


@dataclass
class MemoryItem:
    """A single item in semantic memory."""

    id: Optional[str] = None
    content: str = ""
    item_type: str = (
        "fact"  # fact, belief, hypothesis, goal, observation, trace, memory_log, curated_memory
    )
    confidence: float = 0.5
    domain: str = "general"
    source_model: Optional[str] = None
    embedding: Optional[List[float]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    retrieval_count: int = 0
    last_retrieved_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


@dataclass
class MemoryEdge:
    """An edge connecting two memory items."""

    id: Optional[str] = None
    source_id: str = ""
    target_id: str = ""
    relation: str = "supports"  # supports, contradicts, derived_from, evidence_for
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class MemoryEvent:
    """A raw episodic event."""

    id: Optional[str] = None
    event_type: str = ""  # tool_call, observation, inference, plan_update, etc.
    payload: Dict[str, Any] = field(default_factory=dict)
    session_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Episode:
    """A compressed episodic chunk."""

    id: Optional[str] = None
    summary: str = ""
    embedding: Optional[List[float]] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    event_count: int = 0
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


class PgMemoryStore:
    """
    PostgreSQL-backed memory store with pgvector support.

    This is the warm memory layer for the Vecna hive mind substrate.
    Provides semantic search, memory graphs, and episodic storage.
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        embedding_model: str = "text-embedding-3-small",
        embedding_dim: int = 1536,
        redis_cache=None,
        embedder=None,
    ):
        """
        Initialize the PostgreSQL memory store.

        Args:
            connection_string: PostgreSQL connection URL.
                If None, reads from VECNA_PG_URL environment variable.
            embedding_model: OpenAI embedding model to use.
            embedding_dim: Embedding dimension (must match model).
            redis_cache: Optional RedisHotCache instance for embedding caching.
            embedder: Optional callable that takes List[str] and returns np.ndarray of embeddings.
                If provided, bypasses OpenAI. Useful for testing.
        """
        self.connection_string = connection_string or os.environ.get("VECNA_PG_URL")
        if not self.connection_string:
            raise ValueError(
                "PgMemoryStore requires a connection string. "
                "Pass it directly or set VECNA_PG_URL environment variable."
            )

        self.embedding_model = embedding_model
        self.embedding_dim = embedding_dim
        self._redis_cache = redis_cache
        self._custom_embedder = embedder

        # Lazy initialization
        self._conn = None
        self._embed_client = None

        self._psycopg2 = None
        self._embedding_cache: Dict[str, List[float]] = {}

        # Import psycopg2
        try:
            import psycopg2
            import psycopg2.extras

            self._psycopg2 = psycopg2
            self._psycopg2_extras = psycopg2.extras
        except ImportError:
            raise ImportError(
                "psycopg2 is required for PgMemoryStore. Install with: pip install psycopg2-binary"
            )

    def _get_connection(self):
        """Get or create a database connection."""
        if self._conn is None or self._conn.closed:
            self._conn = self._psycopg2.connect(self.connection_string)
            self._conn.autocommit = False

            # Register vector type adapter
            try:
                from pgvector.psycopg2 import register_vector

                register_vector(self._conn)
            except ImportError:
                # Manual vector handling if pgvector package not installed
                logger.warning("pgvector package not installed, using manual vector handling")

        return self._conn

    def _get_embedder(self):
        """
        Lazy initialization of embedding client.

        Embedding routing:
        1. If custom embedder provided: Use it directly (useful for testing)
        2. If OPENAI_API_KEY is set: Use OpenAI embeddings (1536 dim)
        3. Raise error: Inform user to set OPENAI_API_KEY
        """
        import os

        # Use custom embedder if provided (useful for testing)
        if self._custom_embedder is not None:
            return self._custom_embedder

        # Try OpenAI if API key is available
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            if self._embed_client is None:
                try:
                    from openai import OpenAI

                    self._embed_client = OpenAI(api_key=openai_key)
                    # Ensure dimension is set for OpenAI
                    self.embedding_dim = 1536
                except ImportError:
                    raise ImportError(
                        "openai package required for embeddings. "
                        "Install with: pip install 'vecna[embeddings]'"
                    )
            return self._embed_client

        # No OpenAI key and no custom embedder — cannot proceed
        raise RuntimeError(
            "OPENAI_API_KEY environment variable is required for embeddings. "
            "Set it in your .env file or environment:\n"
            "  export OPENAI_API_KEY=sk-...\n"
            "Alternatively, pass a custom embedder= callable to PgMemoryStore for testing."
        )

    # ============================================================
    # EMBEDDING OPERATIONS
    # ============================================================

    def _content_hash(self, content: str) -> str:
        """Generate a hash for content (used for embedding cache)."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def embed(self, texts: List[str]) -> np.ndarray:
        """
        Generate embeddings for texts.

        Uses multi-tier caching:
        1. In-memory cache (fastest)
        2. Redis cache if available (shared across processes)
        3. Generate new embedding if not cached

        Supports OpenAI embeddings and custom callable embedders.
        """
        if not texts:
            return np.array([])

        # Filter out empty strings
        texts = [t for t in texts if t and t.strip()]
        if not texts:
            return np.array([])

        embedder = self._get_embedder()

        # Check cache and identify texts that need embedding
        results = []
        texts_to_embed = []
        text_indices = []

        for i, text in enumerate(texts):
            cache_key = self._content_hash(text)

            # Check in-memory cache first
            if cache_key in self._embedding_cache:
                results.append((i, self._embedding_cache[cache_key]))
                continue

            # Check Redis cache if available
            if self._redis_cache:
                try:
                    cached = self._redis_cache.get_embedding(text)
                    if cached is not None:
                        # Store in local cache for faster future access
                        self._embedding_cache[cache_key] = cached
                        results.append((i, cached))
                        continue
                except Exception:
                    pass  # Redis unavailable, continue without

            # Need to generate embedding
            texts_to_embed.append(text)
            text_indices.append(i)

        # Embed uncached texts
        if texts_to_embed:
            if callable(embedder) and not hasattr(embedder, "embeddings"):
                # Custom embedder function: takes list of texts, returns np.ndarray
                new_embeddings = embedder(texts_to_embed)
                for j, embedding in enumerate(new_embeddings):
                    original_idx = text_indices[j]
                    embedding_list = (
                        embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
                    )
                    results.append((original_idx, embedding_list))

                    # Cache the embedding in memory
                    cache_key = self._content_hash(texts_to_embed[j])
                    self._embedding_cache[cache_key] = embedding_list

                    # Cache in Redis if available
                    if self._redis_cache:
                        try:
                            self._redis_cache.set_embedding(texts_to_embed[j], embedding_list)
                        except Exception:
                            pass
            else:
                # OpenAI API
                response = embedder.embeddings.create(
                    model=self.embedding_model, input=texts_to_embed
                )

                for j, item in enumerate(response.data):
                    embedding = item.embedding
                    original_idx = text_indices[j]
                    results.append((original_idx, embedding))

                    # Cache the embedding in memory
                    cache_key = self._content_hash(texts_to_embed[j])
                    self._embedding_cache[cache_key] = embedding

                    # Cache in Redis if available
                    if self._redis_cache:
                        try:
                            self._redis_cache.set_embedding(texts_to_embed[j], embedding)
                        except Exception:
                            pass

        # Sort results by original index
        results.sort(key=lambda x: x[0])
        embeddings = [r[1] for r in results]

        return np.array(embeddings)

    def _format_vector(self, embedding: List[float]) -> str:
        """Format embedding as PostgreSQL vector literal."""
        return "[" + ",".join(str(x) for x in embedding) + "]"

    # ============================================================
    # MEMORY ITEM OPERATIONS
    # ============================================================

    def add_item(self, item: MemoryItem) -> Optional[str]:
        """
        Add a memory item to the store.

        Generates embedding if not present.
        Returns the item ID if successful.
        """
        conn = self._get_connection()

        try:
            # Generate embedding if not present
            if item.embedding is None:
                embeddings = self.embed([item.content])
                if len(embeddings) > 0:
                    item.embedding = embeddings[0].tolist()

            with conn.cursor() as cur:
                embedding_str = self._format_vector(item.embedding) if item.embedding else None

                cur.execute(
                    """
                    INSERT INTO memory_items 
                    (content, item_type, confidence, domain, source_model, 
                     embedding, metadata, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s::vector, %s::jsonb, NOW(), NOW())
                    RETURNING id
                """,
                    (
                        item.content,
                        item.item_type,
                        item.confidence,
                        item.domain,
                        item.source_model,
                        embedding_str,
                        json.dumps(item.metadata),
                    ),
                )

                item_id = str(cur.fetchone()[0])

            conn.commit()
            logger.debug(f"Added memory item {item_id}")
            return item_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add memory item: {e}")
            return None

    def add_items_batch(self, items: List[MemoryItem]) -> List[str]:
        """
        Add multiple memory items in a batch.

        More efficient than individual adds for bulk operations.
        """
        if not items:
            return []

        conn = self._get_connection()

        try:
            # Generate embeddings for items without them
            texts_to_embed = []
            embed_indices = []

            for i, item in enumerate(items):
                if item.embedding is None:
                    # Only include non-empty content (embed() filters these out)
                    if item.content and item.content.strip():
                        texts_to_embed.append(item.content)
                        embed_indices.append(i)

            if texts_to_embed:
                embeddings = self.embed(texts_to_embed)
                # Verify we got the expected number of embeddings
                if len(embeddings) == len(embed_indices):
                    for j, idx in enumerate(embed_indices):
                        items[idx].embedding = embeddings[j].tolist()
                else:
                    logger.warning(
                        f"Embedding count mismatch: expected {len(embed_indices)}, got {len(embeddings)}"
                    )

            # Batch insert
            item_ids = []
            with conn.cursor() as cur:
                for item in items:
                    embedding_str = self._format_vector(item.embedding) if item.embedding else None

                    cur.execute(
                        """
                        INSERT INTO memory_items 
                        (content, item_type, confidence, domain, source_model, 
                         embedding, metadata, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s::vector, %s::jsonb, NOW(), NOW())
                        RETURNING id
                    """,
                        (
                            item.content,
                            item.item_type,
                            item.confidence,
                            item.domain,
                            item.source_model,
                            embedding_str,
                            json.dumps(item.metadata),
                        ),
                    )

                    item_ids.append(str(cur.fetchone()[0]))

            conn.commit()
            logger.debug(f"Added {len(item_ids)} memory items in batch")
            return item_ids

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add memory items batch: {e}")
            return []

    def get_item(self, item_id: str) -> Optional[MemoryItem]:
        """Get a memory item by ID."""
        conn = self._get_connection()

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, content, item_type, confidence, domain, source_model,
                           embedding, metadata, retrieval_count, last_retrieved_at,
                           created_at, updated_at
                    FROM memory_items
                    WHERE id = %s
                """,
                    (item_id,),
                )

                row = cur.fetchone()

            if row is None:
                return None

            return MemoryItem(
                id=str(row[0]),
                content=row[1],
                item_type=row[2],
                confidence=row[3],
                domain=row[4],
                source_model=row[5],
                embedding=list(row[6]) if row[6] is not None else None,
                metadata=row[7] or {},
                retrieval_count=row[8] or 0,
                last_retrieved_at=row[9],
                created_at=row[10],
                updated_at=row[11],
            )

        except Exception as e:
            logger.error(f"Failed to get memory item: {e}")
            return None

    def update_item(self, item_id: str, **kwargs) -> bool:
        """
        Update a memory item.

        Pass any MemoryItem fields as kwargs to update them.
        """
        conn = self._get_connection()

        allowed_fields = {
            "content",
            "item_type",
            "confidence",
            "domain",
            "source_model",
            "embedding",
            "metadata",
        }

        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return True

        try:
            set_clauses = []
            values = []

            for field, value in updates.items():
                if field == "embedding" and value is not None:
                    set_clauses.append(f"{field} = %s::vector")
                    values.append(self._format_vector(value))
                elif field == "metadata":
                    set_clauses.append(f"{field} = %s::jsonb")
                    values.append(json.dumps(value))
                else:
                    set_clauses.append(f"{field} = %s")
                    values.append(value)

            set_clauses.append("updated_at = NOW()")
            values.append(item_id)

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE memory_items 
                    SET {", ".join(set_clauses)}
                    WHERE id = %s
                """,
                    values,
                )

            conn.commit()
            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update memory item: {e}")
            return False

    def delete_item(self, item_id: str) -> bool:
        """Delete a memory item (cascades to edges)."""
        conn = self._get_connection()

        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM memory_items WHERE id = %s", (item_id,))
            conn.commit()
            return True
        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete memory item: {e}")
            return False

    # ============================================================
    # SEMANTIC SEARCH
    # ============================================================

    def search(
        self,
        query: str,
        top_k: int = 10,
        item_type: Optional[str] = None,
        min_confidence: float = 0.0,
        domain: Optional[str] = None,
        hybrid: bool = True,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
        min_vector_score: float = 0.0,
    ) -> List[Tuple[MemoryItem, float]]:
        """
        Semantic search over memory items.

        Uses pgvector for ANN search with cosine similarity and optionally
        combines full-text search scores for hybrid retrieval.
        Returns list of (item, similarity_score) tuples.
        """
        conn = self._get_connection()

        try:
            # Embed query
            query_embedding = self.embed([query])[0]
            query_vector = self._format_vector(query_embedding.tolist())

            # Build query with filters
            where_clauses = ["embedding IS NOT NULL"]
            filter_params = []

            if item_type:
                where_clauses.append("item_type = %s")
                filter_params.append(item_type)

            if min_confidence > 0:
                where_clauses.append("confidence >= %s")
                filter_params.append(min_confidence)

            if domain:
                where_clauses.append("domain = %s")
                filter_params.append(domain)

            has_text_tokens = any(ch.isalnum() for ch in query)

            if hybrid and has_text_tokens:
                query_sql = f"""
                    WITH vector_scores AS (
                        SELECT id, 1 - (embedding <=> %s::vector) AS vec_score
                        FROM memory_items
                        WHERE {" AND ".join(where_clauses)}
                        AND 1 - (embedding <=> %s::vector) > %s
                    ),
                    text_scores AS (
                        SELECT id, ts_rank_cd(search_vector,
                            plainto_tsquery('english', %s)) AS text_score
                        FROM memory_items
                        WHERE search_vector @@ plainto_tsquery('english', %s)
                    )
                    SELECT m.id, m.content, m.item_type, m.confidence, m.domain, m.source_model,
                           m.embedding, m.metadata, m.retrieval_count, m.last_retrieved_at,
                           m.created_at, m.updated_at,
                           COALESCE(v.vec_score, 0) * %s + COALESCE(t.text_score, 0) * %s
                           AS similarity
                    FROM memory_items m
                    LEFT JOIN vector_scores v ON m.id = v.id
                    LEFT JOIN text_scores t ON m.id = t.id
                    WHERE v.id IS NOT NULL OR t.id IS NOT NULL
                    ORDER BY similarity DESC
                    LIMIT %s
                """

                final_params = (
                    [query_vector, query_vector, min_vector_score]
                    + filter_params
                    + [query, query, vector_weight, text_weight, top_k]
                )
            else:
                query_sql = f"""
                    SELECT id, content, item_type, confidence, domain, source_model,
                           embedding, metadata, retrieval_count, last_retrieved_at,
                           created_at, updated_at,
                           1 - (embedding <=> %s::vector) as similarity
                    FROM memory_items
                    WHERE {" AND ".join(where_clauses)}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """
                final_params = [query_vector] + filter_params + [query_vector, top_k]

            with conn.cursor() as cur:
                cur.execute(query_sql, final_params)
                rows = cur.fetchall()

            # Update retrieval counts
            if rows:
                item_ids = [str(row[0]) for row in rows]
                self._update_retrieval_stats(item_ids)

            results = []
            for row in rows:
                item = MemoryItem(
                    id=str(row[0]),
                    content=row[1],
                    item_type=row[2],
                    confidence=row[3],
                    domain=row[4],
                    source_model=row[5],
                    embedding=list(row[6]) if row[6] is not None else None,
                    metadata=row[7] or {},
                    retrieval_count=row[8] or 0,
                    last_retrieved_at=row[9],
                    created_at=row[10],
                    updated_at=row[11],
                )
                similarity = row[12]
                results.append((item, similarity))

            return results

        except Exception as e:
            logger.error(f"Failed to search memory: {e}")
            return []

    def _update_retrieval_stats(self, item_ids: List[str]) -> None:
        """Update retrieval count and timestamp for retrieved items."""
        if not item_ids:
            return

        conn = self._get_connection()

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE memory_items 
                    SET retrieval_count = retrieval_count + 1,
                        last_retrieved_at = NOW()
                    WHERE id = ANY(%s::uuid[])
                """,
                    (item_ids,),
                )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.warning(f"Failed to update retrieval stats: {e}")

    # ============================================================
    # MEMORY EDGES (GRAPH)
    # ============================================================

    def add_edge(self, edge: MemoryEdge) -> Optional[str]:
        """Add an edge between two memory items."""
        conn = self._get_connection()

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO memory_edges 
                    (source_id, target_id, relation, weight, metadata, created_at)
                    VALUES (%s, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (source_id, target_id, relation) DO UPDATE SET
                        weight = EXCLUDED.weight,
                        metadata = EXCLUDED.metadata
                    RETURNING id
                """,
                    (
                        edge.source_id,
                        edge.target_id,
                        edge.relation,
                        edge.weight,
                        json.dumps(edge.metadata),
                    ),
                )

                edge_id = str(cur.fetchone()[0])

            conn.commit()
            return edge_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add memory edge: {e}")
            return None

    def get_edges(
        self,
        item_id: str,
        direction: str = "both",  # "outgoing", "incoming", "both"
        relation: Optional[str] = None,
    ) -> List[MemoryEdge]:
        """Get edges connected to a memory item."""
        conn = self._get_connection()

        try:
            where_parts = []
            params = []

            if direction == "outgoing":
                where_parts.append("source_id = %s")
                params.append(item_id)
            elif direction == "incoming":
                where_parts.append("target_id = %s")
                params.append(item_id)
            else:  # both
                where_parts.append("(source_id = %s OR target_id = %s)")
                params.extend([item_id, item_id])

            if relation:
                where_parts.append("relation = %s")
                params.append(relation)

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, source_id, target_id, relation, weight, metadata, created_at
                    FROM memory_edges
                    WHERE {" AND ".join(where_parts)}
                """,
                    params,
                )

                rows = cur.fetchall()

            return [
                MemoryEdge(
                    id=str(row[0]),
                    source_id=str(row[1]),
                    target_id=str(row[2]),
                    relation=row[3],
                    weight=row[4],
                    metadata=row[5] or {},
                    created_at=row[6],
                )
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Failed to get memory edges: {e}")
            return []

    def get_related_items(
        self, item_id: str, relation: Optional[str] = None, max_depth: int = 1
    ) -> List[Tuple[MemoryItem, float, List[str]]]:
        """
        Get items related to a given item via edges.

        Returns list of (item, path_weight, path) tuples.
        """
        conn = self._get_connection()

        try:
            # For now, simple 1-hop traversal
            # TODO: Implement recursive CTE for deeper traversal

            where_clause = "source_id = %s OR target_id = %s"
            params = [item_id, item_id]

            if relation:
                where_clause = f"({where_clause}) AND relation = %s"
                params.append(relation)

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT DISTINCT ON (mi.id)
                        mi.id, mi.content, mi.item_type, mi.confidence, mi.domain,
                        mi.source_model, mi.embedding, mi.metadata, mi.retrieval_count,
                        mi.last_retrieved_at, mi.created_at, mi.updated_at,
                        me.weight, me.relation
                    FROM memory_edges me
                    JOIN memory_items mi ON (
                        (me.source_id = %s AND me.target_id = mi.id) OR
                        (me.target_id = %s AND me.source_id = mi.id)
                    )
                    WHERE {where_clause}
                """,
                    [item_id, item_id] + params,
                )

                rows = cur.fetchall()

            results = []
            for row in rows:
                item = MemoryItem(
                    id=str(row[0]),
                    content=row[1],
                    item_type=row[2],
                    confidence=row[3],
                    domain=row[4],
                    source_model=row[5],
                    embedding=list(row[6]) if row[6] is not None else None,
                    metadata=row[7] or {},
                    retrieval_count=row[8] or 0,
                    last_retrieved_at=row[9],
                    created_at=row[10],
                    updated_at=row[11],
                )
                weight = row[12]
                relation_type = row[13]
                path = [item_id, relation_type, str(row[0])]
                results.append((item, weight, path))

            return results

        except Exception as e:
            logger.error(f"Failed to get related items: {e}")
            return []

    # ============================================================
    # EPISODIC EVENTS
    # ============================================================

    def add_event(self, event: MemoryEvent) -> Optional[str]:
        """Add an episodic event to the stream."""
        conn = self._get_connection()

        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO memory_events 
                    (event_type, payload, session_id, created_at)
                    VALUES (%s, %s::jsonb, %s, NOW())
                    RETURNING id
                """,
                    (event.event_type, json.dumps(event.payload), event.session_id),
                )

                event_id = str(cur.fetchone()[0])

            conn.commit()
            return event_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add memory event: {e}")
            return None

    def get_recent_events(
        self,
        limit: int = 100,
        event_type: Optional[str] = None,
        session_id: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> List[MemoryEvent]:
        """Get recent events from the episodic stream."""
        conn = self._get_connection()

        try:
            where_parts = []
            params = []

            if event_type:
                where_parts.append("event_type = %s")
                params.append(event_type)

            if session_id:
                where_parts.append("session_id = %s")
                params.append(session_id)

            if since:
                where_parts.append("created_at >= %s")
                params.append(since)

            where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
            params.append(limit)

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, event_type, payload, session_id, created_at
                    FROM memory_events
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s
                """,
                    params,
                )

                rows = cur.fetchall()

            return [
                MemoryEvent(
                    id=str(row[0]),
                    event_type=row[1],
                    payload=row[2] or {},
                    session_id=row[3],
                    created_at=row[4],
                )
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Failed to get recent events: {e}")
            return []

    # ============================================================
    # EPISODES (COMPRESSED)
    # ============================================================

    def add_episode(self, episode: Episode) -> Optional[str]:
        """Add a compressed episode."""
        conn = self._get_connection()

        try:
            # Generate embedding if not present
            if episode.embedding is None and episode.summary:
                embeddings = self.embed([episode.summary])
                if len(embeddings) > 0:
                    episode.embedding = embeddings[0].tolist()

            with conn.cursor() as cur:
                embedding_str = (
                    self._format_vector(episode.embedding) if episode.embedding else None
                )

                cur.execute(
                    """
                    INSERT INTO episodes 
                    (summary, embedding, start_time, end_time, event_count, 
                     tags, metadata, created_at)
                    VALUES (%s, %s::vector, %s, %s, %s, %s, %s::jsonb, NOW())
                    RETURNING id
                """,
                    (
                        episode.summary,
                        embedding_str,
                        episode.start_time,
                        episode.end_time,
                        episode.event_count,
                        episode.tags,
                        json.dumps(episode.metadata),
                    ),
                )

                episode_id = str(cur.fetchone()[0])

            conn.commit()
            return episode_id

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to add episode: {e}")
            return None

    def search_episodes(
        self,
        query: str,
        top_k: int = 5,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Tuple[Episode, float]]:
        """Search episodes by semantic similarity."""
        conn = self._get_connection()

        try:
            query_embedding = self.embed([query])[0]
            query_vector = self._format_vector(query_embedding.tolist())

            where_clauses = ["embedding IS NOT NULL"]
            filter_params = []

            if start_time:
                where_clauses.append("start_time >= %s")
                filter_params.append(start_time)

            if end_time:
                where_clauses.append("end_time <= %s")
                filter_params.append(end_time)

            # Parameter order: similarity_calc, [filters], order_by, limit
            final_params = [query_vector] + filter_params + [query_vector, top_k]

            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT id, summary, embedding, start_time, end_time, event_count,
                           tags, metadata, created_at,
                           1 - (embedding <=> %s::vector) as similarity
                    FROM episodes
                    WHERE {" AND ".join(where_clauses)}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                """,
                    final_params,
                )

                rows = cur.fetchall()

            return [
                (
                    Episode(
                        id=str(row[0]),
                        summary=row[1],
                        embedding=list(row[2]) if row[2] is not None else None,
                        start_time=row[3],
                        end_time=row[4],
                        event_count=row[5],
                        tags=row[6] or [],
                        metadata=row[7] or {},
                        created_at=row[8],
                    ),
                    row[9],  # similarity
                )
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Failed to search episodes: {e}")
            return []

    # ============================================================
    # RLM-STYLE RETRIEVAL
    # ============================================================

    def decompose_query(self, query: str) -> List[str]:
        """
        Decompose a complex query into atomic facets.

        Same logic as MemoryStore.decompose_query for compatibility.
        """
        import re

        facets = [query]
        query_lower = query.lower()

        # Remove question prefixes
        for prefix in [
            "what ",
            "how ",
            "why ",
            "when ",
            "where ",
            "which ",
            "can ",
            "does ",
            "is ",
            "are ",
        ]:
            if query_lower.startswith(prefix):
                query_lower = query_lower[len(prefix) :]
                break

        # Split on conjunctions
        for conj in [" and ", " or ", " but ", " vs ", " versus ", ", "]:
            if conj in query_lower:
                parts = query_lower.split(conj)
                facets.extend([p.strip() for p in parts if p.strip() and len(p.strip()) > 3])

        # Extract entities (capitalized words)
        entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", query)
        facets.extend(entities)

        # Extract technical terms
        tech_terms = re.findall(r"\b[a-z]+[A-Z][a-zA-Z]*\b|\b\w+[-_]\w+\b", query)
        facets.extend(tech_terms)

        # Deduplicate
        seen = set()
        unique_facets = []
        for f in facets:
            f_lower = f.lower().strip()
            if f_lower not in seen and len(f_lower) > 2:
                seen.add(f_lower)
                unique_facets.append(f.strip())

        return unique_facets[:8]

    def rlm_retrieve(
        self,
        query: str,
        top_k_per_facet: int = 5,
        max_items: int = 20,
        max_chars: int = 4000,
        include_episodes: bool = True,
    ) -> Tuple[str, List[str], Dict[str, int]]:
        """
        Full RLM retrieval pipeline: decompose → retrieve → recompose.

        Returns:
            - context: The recomposed evidence string
            - facets: The decomposed facets
            - stats: Retrieval statistics
        """
        # Decompose
        facets = self.decompose_query(query)

        # Retrieve per facet
        all_results: Dict[str, List[Tuple[MemoryItem, float]]] = {}
        for facet in facets:
            results = self.search(facet, top_k=top_k_per_facet)
            all_results[facet] = results

        # Optionally search episodes
        episode_results = []
        if include_episodes:
            episode_results = self.search_episodes(query, top_k=3)

        # Stats
        stats = {
            "num_facets": len(facets),
            "total_items_retrieved": sum(len(r) for r in all_results.values()),
            "facets_with_results": sum(1 for r in all_results.values() if r),
            "episodes_retrieved": len(episode_results),
        }

        # Recompose
        context = self._recompose_evidence(all_results, episode_results, max_items, max_chars)

        return context, facets, stats

    def _recompose_evidence(
        self,
        facet_results: Dict[str, List[Tuple[MemoryItem, float]]],
        episode_results: List[Tuple[Episode, float]],
        max_items: int,
        max_chars: int,
    ) -> str:
        """Recompose retrieved evidence into a structured context string."""
        # Collect unique items
        item_scores: Dict[str, Tuple[MemoryItem, float, str]] = {}

        for facet, results in facet_results.items():
            for item, score in results:
                if item.id not in item_scores or score > item_scores[item.id][1]:
                    item_scores[item.id] = (item, score, facet)

        sorted_items = sorted(item_scores.values(), key=lambda x: x[1], reverse=True)

        if not sorted_items and not episode_results:
            return "No relevant evidence found."

        lines = ["## Retrieved Evidence"]
        total_chars = len(lines[0])
        items_added = 0

        # Add memory items
        for item, score, facet in sorted_items[:max_items]:
            if total_chars >= max_chars:
                break

            line = f"- [{item.item_type}][{item.confidence:.1f}][sim:{score:.2f}] {item.content}"
            if total_chars + len(line) > max_chars:
                break

            lines.append(line)
            total_chars += len(line)
            items_added += 1

        # Add episodes
        if episode_results and total_chars < max_chars:
            lines.append("\n### Relevant Episodes")
            for episode, score in episode_results[:3]:
                if total_chars >= max_chars:
                    break
                line = f"- [episode][sim:{score:.2f}] {episode.summary[:200]}..."
                if total_chars + len(line) > max_chars:
                    break
                lines.append(line)
                total_chars += len(line)

        return "\n".join(lines)

    def get_relevant_context(self, query: str, max_items: int = 15, max_chars: int = 3000) -> str:
        """
        Get relevant memory items formatted as context string.

        Simpler interface than rlm_retrieve for basic use cases.
        """
        context, _, _ = self.rlm_retrieve(
            query,
            top_k_per_facet=5,
            max_items=max_items,
            max_chars=max_chars,
            include_episodes=True,
        )
        return context

    # ============================================================
    # STATISTICS
    # ============================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get memory store statistics."""
        conn = self._get_connection()

        try:
            stats = {}

            with conn.cursor() as cur:
                # Memory items
                cur.execute("SELECT COUNT(*) FROM memory_items")
                stats["total_items"] = cur.fetchone()[0]

                cur.execute("""
                    SELECT item_type, COUNT(*) 
                    FROM memory_items 
                    GROUP BY item_type
                """)
                stats["items_by_type"] = dict(cur.fetchall())

                cur.execute("SELECT AVG(confidence) FROM memory_items")
                stats["avg_confidence"] = float(cur.fetchone()[0] or 0)

                # Edges
                cur.execute("SELECT COUNT(*) FROM memory_edges")
                stats["total_edges"] = cur.fetchone()[0]

                cur.execute("""
                    SELECT relation, COUNT(*) 
                    FROM memory_edges 
                    GROUP BY relation
                """)
                stats["edges_by_relation"] = dict(cur.fetchall())

                # Events
                cur.execute("SELECT COUNT(*) FROM memory_events")
                stats["total_events"] = cur.fetchone()[0]

                # Episodes
                cur.execute("SELECT COUNT(*) FROM episodes")
                stats["total_episodes"] = cur.fetchone()[0]

            return stats

        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}

    # ============================================================
    # STATE INTEGRATION
    # ============================================================

    def add_from_state(self, state) -> Dict[str, int]:
        """
        Add all items from HiveState to memory_items table with deduplication.

        Maps HiveState item types to memory items:
        - facts → item_type="fact"
        - beliefs → item_type="belief"
        - hypotheses → item_type="hypothesis"
        - goals → item_type="goal"
        - plans → item_type="plan"
        - open_questions → item_type="open_question"
        - contradictions → item_type="contradiction"

        Deduplication is done via content+item_type hash to prevent duplicates.

        Args:
            state: HiveState object

        Returns:
            Dict with counts by type: {fact: 5, belief: 3, ...}
        """
        counts = {
            "fact": 0,
            "belief": 0,
            "hypothesis": 0,
            "goal": 0,
            "plan": 0,
            "open_question": 0,
            "contradiction": 0,
        }

        # Collect all items to add
        items_to_add: List[MemoryItem] = []

        # Facts
        for f in getattr(state, "facts", []):
            items_to_add.append(
                MemoryItem(
                    content=f.content,
                    item_type="fact",
                    confidence=f.confidence,
                    domain=getattr(f, "domain", "general"),
                    source_model=getattr(f, "source_model", None),
                    metadata={
                        "original_id": f.id,
                        "evidence": getattr(f, "evidence", ""),
                        "timestamp": f.timestamp.isoformat() if hasattr(f, "timestamp") else None,
                    },
                )
            )

        # Beliefs
        for b in getattr(state, "beliefs", []):
            items_to_add.append(
                MemoryItem(
                    content=b.content,
                    item_type="belief",
                    confidence=b.confidence,
                    domain="general",
                    source_model=getattr(b, "source_model", None),
                    metadata={
                        "original_id": b.id,
                        "reasoning": getattr(b, "reasoning", ""),
                        "supporting_facts": getattr(b, "supporting_facts", []),
                        "timestamp": b.timestamp.isoformat() if hasattr(b, "timestamp") else None,
                    },
                )
            )

        # Hypotheses
        for h in getattr(state, "hypotheses", []):
            items_to_add.append(
                MemoryItem(
                    content=h.content,
                    item_type="hypothesis",
                    confidence=h.confidence,
                    domain="general",
                    source_model=getattr(h, "source_model", None),
                    metadata={
                        "original_id": h.id,
                        "exploration_notes": getattr(h, "exploration_notes", ""),
                        "status": getattr(h, "status", "active"),
                        "timestamp": h.timestamp.isoformat() if hasattr(h, "timestamp") else None,
                    },
                )
            )

        # Goals
        for g in getattr(state, "goals", []):
            items_to_add.append(
                MemoryItem(
                    content=g.content,
                    item_type="goal",
                    confidence=0.8,  # Goals don't have confidence, use high default
                    domain="general",
                    source_model=None,
                    metadata={
                        "original_id": g.id,
                        "priority": getattr(g, "priority", "medium"),
                        "status": getattr(g, "status", "active"),
                        "sub_goals": getattr(g, "sub_goals", []),
                        "progress_notes": getattr(g, "progress_notes", ""),
                        "timestamp": g.timestamp.isoformat() if hasattr(g, "timestamp") else None,
                    },
                )
            )

        # Plans
        for p in getattr(state, "plans", []):
            # Serialize steps into content
            steps_content = " -> ".join(getattr(p, "steps", []))
            content = f"Plan for goal {p.goal_id}: {steps_content}"
            items_to_add.append(
                MemoryItem(
                    content=content,
                    item_type="plan",
                    confidence=0.7,
                    domain="general",
                    source_model=None,
                    metadata={
                        "original_id": p.id,
                        "goal_id": p.goal_id,
                        "steps": getattr(p, "steps", []),
                        "current_step": getattr(p, "current_step", 0),
                        "status": getattr(p, "status", "pending"),
                        "timestamp": p.timestamp.isoformat() if hasattr(p, "timestamp") else None,
                    },
                )
            )

        # Open Questions
        for q in getattr(state, "open_questions", []):
            items_to_add.append(
                MemoryItem(
                    content=q.question,
                    item_type="open_question",
                    confidence=0.5,
                    domain="general",
                    source_model=None,
                    metadata={
                        "original_id": q.id,
                        "context": getattr(q, "context", ""),
                        "priority": getattr(q, "priority", "medium"),
                        "assigned_domains": getattr(q, "assigned_domains", []),
                        "status": getattr(q, "status", "open"),
                        "timestamp": q.timestamp.isoformat() if hasattr(q, "timestamp") else None,
                    },
                )
            )

        # Contradictions
        for c in getattr(state, "contradictions", []):
            content = f"Contradiction: {c.item_a_content} vs {c.item_b_content}"
            items_to_add.append(
                MemoryItem(
                    content=content,
                    item_type="contradiction",
                    confidence=0.9,  # High confidence that this IS a contradiction
                    domain="general",
                    source_model=None,
                    metadata={
                        "original_id": c.id,
                        "item_a_id": c.item_a_id,
                        "item_a_content": c.item_a_content,
                        "item_b_id": c.item_b_id,
                        "item_b_content": c.item_b_content,
                        "source_models": getattr(c, "source_models", []),
                        "resolution_status": getattr(c, "resolution_status", "unresolved"),
                        "resolution_notes": getattr(c, "resolution_notes", ""),
                        "timestamp": c.timestamp.isoformat() if hasattr(c, "timestamp") else None,
                    },
                )
            )

        # Upsert with deduplication
        if items_to_add:
            counts = self._upsert_items_with_dedupe(items_to_add)

        return counts

    def _content_type_hash(self, content: str, item_type: str) -> str:
        """Generate a hash for content+type combination (used for deduplication)."""
        combined = f"{item_type}:{content}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]

    def _upsert_items_with_dedupe(self, items: List[MemoryItem]) -> Dict[str, int]:
        """
        Upsert memory items with deduplication by content+item_type hash.

        Uses PostgreSQL ON CONFLICT to update existing items or insert new ones.

        Args:
            items: List of MemoryItem objects to upsert

        Returns:
            Dict with counts by type
        """
        if not items:
            return {}

        conn = self._get_connection()
        counts = {}

        try:
            # Generate embeddings for items without them
            texts_to_embed = []
            embed_indices = []

            for i, item in enumerate(items):
                if item.embedding is None:
                    # Only include non-empty content (embed() filters these out)
                    if item.content and item.content.strip():
                        texts_to_embed.append(item.content)
                        embed_indices.append(i)

            if texts_to_embed:
                embeddings = self.embed(texts_to_embed)
                # Verify we got the expected number of embeddings
                if len(embeddings) == len(embed_indices):
                    for j, idx in enumerate(embed_indices):
                        items[idx].embedding = embeddings[j].tolist()
                else:
                    logger.warning(
                        f"Embedding count mismatch: expected {len(embed_indices)}, got {len(embeddings)}"
                    )

            # Upsert each item
            with conn.cursor() as cur:
                for item in items:
                    content_hash = self._content_type_hash(item.content, item.item_type)
                    embedding_str = self._format_vector(item.embedding) if item.embedding else None

                    # Add content_hash to metadata for tracking
                    metadata = item.metadata.copy() if item.metadata else {}
                    metadata["content_hash"] = content_hash

                    cur.execute(
                        """
                        INSERT INTO memory_items 
                        (content, item_type, confidence, domain, source_model, 
                         embedding, metadata, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s::vector, %s::jsonb, NOW(), NOW())
                        ON CONFLICT ON CONSTRAINT memory_items_content_type_unique 
                        DO UPDATE SET
                            confidence = GREATEST(memory_items.confidence, EXCLUDED.confidence),
                            metadata = memory_items.metadata || EXCLUDED.metadata,
                            updated_at = NOW()
                        RETURNING id, (xmax = 0) as inserted
                    """,
                        (
                            item.content,
                            item.item_type,
                            item.confidence,
                            item.domain,
                            item.source_model,
                            embedding_str,
                            json.dumps(metadata),
                        ),
                    )

                    result = cur.fetchone()
                    if result and result[1]:  # inserted=True means new item
                        counts[item.item_type] = counts.get(item.item_type, 0) + 1

            conn.commit()
            logger.debug(f"Upserted memory items: {counts}")
            return counts

        except Exception as e:
            conn.rollback()
            # If the constraint doesn't exist, try simpler approach
            if "memory_items_content_type_unique" in str(e):
                logger.warning("Dedupe constraint not found, using fallback insert")
                return self._fallback_insert_items(items)
            logger.error(f"Failed to upsert memory items: {e}")
            return counts

    def _fallback_insert_items(self, items: List[MemoryItem]) -> Dict[str, int]:
        """
        Fallback insert for when dedupe constraint doesn't exist.

        Checks for existing items manually before inserting.
        """
        conn = self._get_connection()
        counts = {}

        try:
            with conn.cursor() as cur:
                for item in items:
                    # Check if item already exists
                    cur.execute(
                        """
                        SELECT id FROM memory_items 
                        WHERE content = %s AND item_type = %s
                        LIMIT 1
                    """,
                        (item.content, item.item_type),
                    )

                    if cur.fetchone() is not None:
                        # Already exists, skip
                        continue

                    embedding_str = self._format_vector(item.embedding) if item.embedding else None

                    cur.execute(
                        """
                        INSERT INTO memory_items 
                        (content, item_type, confidence, domain, source_model, 
                         embedding, metadata, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s::vector, %s::jsonb, NOW(), NOW())
                    """,
                        (
                            item.content,
                            item.item_type,
                            item.confidence,
                            item.domain,
                            item.source_model,
                            embedding_str,
                            json.dumps(item.metadata or {}),
                        ),
                    )

                    counts[item.item_type] = counts.get(item.item_type, 0) + 1

            conn.commit()
            return counts

        except Exception as e:
            conn.rollback()
            logger.error(f"Fallback insert failed: {e}")
            return counts

    # ============================================================
    # CLEANUP
    # ============================================================

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
            self._conn = None

    def __del__(self):
        """Cleanup on deletion."""
        self.close()
