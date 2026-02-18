"""
PostgreSQL-backed goal queue with in-memory fallback.

Replaces the JSONL file-based GoalQueue with a durable,
concurrent-safe implementation. Supports both PostgreSQL
persistence and an in-memory heap for unit tests and offline mode.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("vecna.orchestrator.pg_goal_queue")


class GoalStatus(str, Enum):
    """Status of a goal in the queue."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


PRIORITY_ORDER: Dict[str, int] = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class GoalItem:
    """A goal in the queue.

    Uses string-based priority names (critical, high, medium, low)
    and supports heapq ordering via __lt__.
    """

    goal: str = ""
    priority: str = "medium"
    goal_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: GoalStatus = GoalStatus.PENDING
    source: str = "manual"  # manual, curiosity, dreamloop, autonomous
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    max_retries: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict with backward-compat 'content' key."""
        return {
            "goal_id": self.goal_id,
            "goal": self.goal,
            "priority": self.priority,
            "status": self.status.value if isinstance(self.status, GoalStatus) else self.status,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "max_retries": self.max_retries,
            "content": self.goal,  # backward compat with old GoalQueue
        }

    def __lt__(self, other: "GoalItem") -> bool:
        """For heapq priority ordering — lower PRIORITY_ORDER value = higher priority."""
        return PRIORITY_ORDER.get(self.priority, 2) < PRIORITY_ORDER.get(other.priority, 2)


class PgGoalQueue:
    """
    Goal queue with PostgreSQL persistence and in-memory fallback.

    For unit tests and offline mode, use_memory_fallback=True.
    For production, connects to the same PG instance as PgMemoryStore.

    The in-memory fallback uses a thread-safe heap with priority ordering.
    The PG backend uses FOR UPDATE SKIP LOCKED for concurrent-safe pop.
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        pg_url: Optional[str] = None,
        use_memory_fallback: bool = False,
    ):
        # Support both parameter names for backward compat
        self.connection_string = connection_string or pg_url or os.environ.get("VECNA_PG_URL")
        self._use_memory = use_memory_fallback or self.connection_string is None

        # In-memory state (used when _use_memory is True)
        self._memory_queue: List[GoalItem] = []
        self._memory_lock = threading.Lock()
        self._completed: Dict[str, GoalItem] = {}
        self._failed: Dict[str, GoalItem] = {}
        # Track all pushed items by ID for mark_completed/mark_failed lookup
        self._all_items: Dict[str, GoalItem] = {}

        # PG state (used when _use_memory is False)
        self._psycopg2: Any = None
        self._psycopg2_extras: Any = None
        self._conn: Any = None

        if not self._use_memory and not self.connection_string:
            raise ValueError(
                "PgGoalQueue requires a connection string. "
                "Pass it directly or set VECNA_PG_URL environment variable."
            )

    # ------------------------------------------------------------------
    # Public API — dispatches to memory or PG backend
    # ------------------------------------------------------------------

    def push(self, item: Union[GoalItem, str], **kwargs: Any) -> Optional[str]:
        """Add a goal to the queue.

        Accepts either a GoalItem (new API) or a raw content string (legacy PG API).
        When called with a string, keyword arguments are forwarded to the PG backend.
        """
        if isinstance(item, GoalItem):
            if self._use_memory:
                self._memory_push(item)
                return item.goal_id
            return self._pg_push_raw(
                content=item.goal,
                priority=PRIORITY_ORDER.get(item.priority, 2),
                max_retries=item.max_retries,
                metadata=item.metadata,
            )
        # Legacy string-based push for PG backend
        return self._pg_push_raw(content=item, **kwargs)

    def pop(self) -> Union[Optional[GoalItem], Optional[Dict[str, Any]]]:
        """Pop the highest-priority pending goal.

        Returns GoalItem in memory mode, Dict in PG mode.
        """
        if self._use_memory:
            return self._memory_pop()
        return self._pg_pop()

    def mark_completed(self, goal_id: str) -> None:
        """Mark a goal as completed."""
        if self._use_memory:
            self._memory_mark_completed(goal_id)
        else:
            self._pg_mark_completed(goal_id)

    def mark_failed(self, goal_id: str, error: str = "") -> Optional[Dict[str, Any]]:
        """Mark a goal as failed."""
        if self._use_memory:
            self._memory_mark_failed(goal_id, error)
            return None
        return self._pg_mark_failed(goal_id, error)

    def list_pending(self) -> List[GoalItem]:
        """List all pending goals."""
        if self._use_memory:
            return self._memory_list_pending()
        return self._pg_list_pending()

    def close(self) -> None:
        """Close the PG connection if open."""
        if self._conn is not None and not self._conn.closed:
            self._conn.close()

    # ------------------------------------------------------------------
    # In-memory backend (thread-safe via lock)
    # ------------------------------------------------------------------

    def _memory_push(self, item: GoalItem) -> None:
        with self._memory_lock:
            heapq.heappush(self._memory_queue, item)
            self._all_items[item.goal_id] = item

    def _memory_pop(self) -> Optional[GoalItem]:
        with self._memory_lock:
            while self._memory_queue:
                item = heapq.heappop(self._memory_queue)
                if item.goal_id not in self._completed and item.goal_id not in self._failed:
                    item.status = GoalStatus.RUNNING
                    return item
            return None

    def _memory_mark_completed(self, goal_id: str) -> None:
        with self._memory_lock:
            if goal_id in self._completed or goal_id in self._failed:
                raise KeyError(f"Goal with id '{goal_id}' is already completed or failed")
            if goal_id not in self._all_items:
                raise KeyError(f"Goal with id '{goal_id}' was not found")
            existing = self._all_items[goal_id]
            existing.status = GoalStatus.COMPLETED
            existing.completed_at = datetime.now()
            self._completed[goal_id] = existing

    def _memory_mark_failed(self, goal_id: str, error: str) -> None:
        with self._memory_lock:
            if goal_id in self._completed or goal_id in self._failed:
                raise KeyError(f"Goal with id '{goal_id}' is already completed or failed")
            if goal_id not in self._all_items:
                raise KeyError(f"Goal with id '{goal_id}' was not found")
            existing = self._all_items[goal_id]
            existing.status = GoalStatus.FAILED
            existing.error = error
            self._failed[goal_id] = existing

    def _memory_list_pending(self) -> List[GoalItem]:
        with self._memory_lock:
            return [
                item
                for item in self._memory_queue
                if item.goal_id not in self._completed and item.goal_id not in self._failed
            ]

    # ------------------------------------------------------------------
    # PostgreSQL backend (preserved from original implementation)
    # ------------------------------------------------------------------

    def _ensure_psycopg2(self) -> None:
        if self._psycopg2 is not None and self._psycopg2_extras is not None:
            return

        try:
            import psycopg2
            import psycopg2.extras

            self._psycopg2 = psycopg2
            self._psycopg2_extras = psycopg2.extras
        except ImportError as exc:
            raise ImportError(
                "psycopg2 is required for PgGoalQueue. Install with: pip install psycopg2-binary"
            ) from exc

    def _dict_cursor(self, conn: Any) -> Any:
        if self._psycopg2_extras is None:
            try:
                self._ensure_psycopg2()
            except ImportError:
                return conn.cursor()
        return conn.cursor(cursor_factory=self._psycopg2_extras.RealDictCursor)

    def _get_connection(self) -> Any:
        if self._conn is not None and not self._conn.closed:
            return self._conn

        self._ensure_psycopg2()

        if self._conn is None or self._conn.closed:
            self._conn = self._psycopg2.connect(self.connection_string)
            self._conn.autocommit = False
        return self._conn

    def _content_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _normalize_row(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if row is None:
            return None

        normalized = dict(row)
        if "goal_id" in normalized:
            normalized["goal_id"] = str(normalized["goal_id"])
        if "content" in normalized:
            normalized["goal"] = normalized["content"]
        return normalized

    def _pg_push_raw(
        self,
        content: str,
        priority: int = 5,
        max_retries: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Push a goal to PostgreSQL (raw string API)."""
        content_hash = self._content_hash(content)
        goal_id = str(uuid.uuid4())
        metadata_payload = metadata or {}
        conn = self._get_connection()

        try:
            with self._dict_cursor(conn) as cur:
                cur.execute(
                    """
                    INSERT INTO autonomy_goals (
                        goal_id,
                        content,
                        content_hash,
                        priority,
                        status,
                        retry_count,
                        max_retries,
                        metadata,
                        scheduled_at,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %s,
                        %s,
                        %s,
                        %s,
                        'pending',
                        0,
                        %s,
                        %s::jsonb,
                        NOW(),
                        NOW(),
                        NOW()
                    )
                    ON CONFLICT (content_hash) DO NOTHING
                    RETURNING goal_id;
                    """,
                    (
                        goal_id,
                        content,
                        content_hash,
                        priority,
                        max_retries,
                        json.dumps(metadata_payload),
                    ),
                )
                inserted = cur.fetchone()

                if inserted is None:
                    cur.execute(
                        "SELECT goal_id FROM autonomy_goals WHERE content_hash = %s;",
                        (content_hash,),
                    )
                    existing = cur.fetchone()
                    conn.commit()
                    if existing is None:
                        raise RuntimeError("Failed to insert or retrieve goal by content hash")
                    return str(existing["goal_id"])

                conn.commit()
                return str(inserted["goal_id"])
        except RuntimeError:
            conn.rollback()
            raise
        except Exception:
            conn.rollback()
            raise

    def _pg_pop(self) -> Optional[Dict[str, Any]]:
        """Pop highest-priority goal from PostgreSQL."""
        conn = self._get_connection()
        try:
            with self._dict_cursor(conn) as cur:
                cur.execute(
                    """
                    WITH next_goal AS (
                        SELECT goal_id
                        FROM autonomy_goals
                        WHERE status = 'pending' AND scheduled_at <= NOW()
                        ORDER BY priority DESC, scheduled_at ASC, created_at ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE autonomy_goals AS goals
                    SET status = 'in_progress', updated_at = NOW()
                    FROM next_goal
                    WHERE goals.goal_id = next_goal.goal_id
                    RETURNING
                        goals.goal_id,
                        goals.content,
                        goals.priority,
                        goals.status,
                        goals.retry_count,
                        goals.max_retries,
                        goals.metadata,
                        goals.scheduled_at,
                        goals.created_at,
                        goals.updated_at;
                    """
                )
                row = cur.fetchone()
                conn.commit()
                return self._normalize_row(row)
        except Exception:
            conn.rollback()
            raise

    def _pg_mark_completed(self, goal_id: str) -> None:
        """Mark a goal as completed in PostgreSQL."""
        conn = self._get_connection()
        goal_exists = True
        try:
            with self._dict_cursor(conn) as cur:
                cur.execute(
                    """
                    UPDATE autonomy_goals
                    SET status = 'completed', completed_at = NOW(), updated_at = NOW()
                    WHERE goal_id = %s
                    RETURNING goal_id;
                    """,
                    (goal_id,),
                )
                row = cur.fetchone()
                goal_exists = row is not None
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        if not goal_exists:
            raise KeyError(f"Goal with id '{goal_id}' was not found")

    def _pg_mark_failed(self, goal_id: str, error: str) -> Optional[Dict[str, Any]]:
        """Mark a goal as failed in PostgreSQL with retry logic."""
        conn = self._get_connection()
        updated_goal = None
        try:
            with self._dict_cursor(conn) as cur:
                cur.execute(
                    """
                    UPDATE autonomy_goals
                    SET
                        retry_count = retry_count + 1,
                        last_error = %s,
                        status = CASE
                            WHEN retry_count + 1 > max_retries THEN 'failed'
                            ELSE 'pending'
                        END,
                        scheduled_at = CASE
                            WHEN retry_count + 1 > max_retries THEN scheduled_at
                            ELSE NOW()
                        END,
                        updated_at = NOW()
                    WHERE goal_id = %s
                    RETURNING goal_id, status, retry_count, max_retries, last_error;
                    """,
                    (error, goal_id),
                )
                row = cur.fetchone()
                if row is not None:
                    updated_goal = self._normalize_row(row)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        if updated_goal is None:
            raise KeyError(f"Goal with id '{goal_id}' was not found")

        return updated_goal

    def _pg_list_pending(self) -> List[GoalItem]:
        """List all pending goals from PostgreSQL."""
        conn = self._get_connection()
        try:
            with self._dict_cursor(conn) as cur:
                cur.execute(
                    """
                    SELECT goal_id, content, priority, status, metadata,
                           created_at, max_retries
                    FROM autonomy_goals
                    WHERE status = 'pending'
                    ORDER BY priority DESC, created_at ASC;
                    """
                )
                rows = cur.fetchall()
            conn.commit()
            return [
                GoalItem(
                    goal_id=str(row["goal_id"]),
                    goal=row["content"],
                    priority=str(row["priority"]),
                    status=GoalStatus.PENDING,
                    max_retries=row.get("max_retries", 0),
                )
                for row in rows
            ]
        except Exception:
            conn.rollback()
            raise
