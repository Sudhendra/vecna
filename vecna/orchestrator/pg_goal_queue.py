"""PostgreSQL-backed priority queue for autonomy goals."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from typing import Any, Dict, Optional


class PgGoalQueue:
    """Priority queue backed by the autonomy_goals PostgreSQL table."""

    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string or os.environ.get("VECNA_PG_URL")
        if not self.connection_string:
            raise ValueError(
                "PgGoalQueue requires a connection string. "
                "Pass it directly or set VECNA_PG_URL environment variable."
            )

        self._psycopg2 = None
        self._psycopg2_extras = None
        self._conn = None

    def _ensure_psycopg2(self) -> None:
        if self._psycopg2 is not None and self._psycopg2_extras is not None:
            return

        try:
            import psycopg2
            import psycopg2.extras

            self._psycopg2 = psycopg2
            self._psycopg2_extras = psycopg2.extras
        except ImportError:
            raise ImportError(
                "psycopg2 is required for PgGoalQueue. Install with: pip install psycopg2-binary"
            )

    def _dict_cursor(self, conn):
        if self._psycopg2_extras is None:
            try:
                self._ensure_psycopg2()
            except ImportError:
                return conn.cursor()
        return conn.cursor(cursor_factory=self._psycopg2_extras.RealDictCursor)

    def _get_connection(self):
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

    def push(
        self,
        content: str,
        priority: int = 5,
        max_retries: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
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
        except Exception:
            conn.rollback()
            raise

    def pop(self) -> Optional[Dict[str, Any]]:
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

    def mark_completed(self, goal_id: str) -> None:
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

    def mark_failed(self, goal_id: str, error: str) -> Optional[Dict[str, Any]]:
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

    def close(self) -> None:
        if self._conn is not None and not self._conn.closed:
            self._conn.close()
