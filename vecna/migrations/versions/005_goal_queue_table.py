"""Add autonomy_goals table for DB-backed goal queue.

Revision ID: 005_goal_queue_table
Revises: 004_sessions_table
Create Date: 2026-02-15
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "005_goal_queue_table"
down_revision: Union[str, None] = "004_sessions_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS autonomy_goals (
            goal_id UUID PRIMARY KEY,
            content TEXT NOT NULL,
            content_hash VARCHAR(64) NOT NULL UNIQUE,
            priority INTEGER NOT NULL DEFAULT 5,
            status VARCHAR(24) NOT NULL DEFAULT 'pending',
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            CHECK (priority >= 0),
            CHECK (retry_count >= 0),
            CHECK (max_retries >= 0),
            CHECK (status IN ('pending', 'in_progress', 'completed', 'failed'))
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS autonomy_goals_status_scheduled_idx
        ON autonomy_goals (status, scheduled_at ASC, priority DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS autonomy_goals_created_at_idx
        ON autonomy_goals (created_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS autonomy_goals_created_at_idx;")
    op.execute("DROP INDEX IF EXISTS autonomy_goals_status_scheduled_idx;")
    op.execute("DROP TABLE IF EXISTS autonomy_goals;")
