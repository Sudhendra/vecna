"""Add sessions table for compact session records.

Revision ID: 004_sessions_table
Revises: 003_memory_search_vector
Create Date: 2026-02-11
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004_sessions_table"
down_revision: Union[str, None] = "003_memory_search_vector"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id UUID PRIMARY KEY,
            started_at TIMESTAMPTZ NOT NULL,
            ended_at TIMESTAMPTZ NOT NULL,
            summary TEXT,
            tokens_used INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS sessions_started_at_idx
        ON sessions (started_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS sessions_started_at_idx;")
    op.execute("DROP TABLE IF EXISTS sessions;")
