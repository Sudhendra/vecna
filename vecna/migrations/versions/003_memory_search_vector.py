"""Add search_vector to memory_items

Revision ID: 003_memory_search_vector
Revises: 002_identity_timeline_columns
Create Date: 2026-02-09
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_memory_search_vector"
down_revision: Union[str, None] = "002_identity_timeline_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE memory_items
        ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', content)) STORED;
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS memory_items_search_vector_idx
        ON memory_items USING GIN (search_vector);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS memory_items_search_vector_idx;")
    op.execute("ALTER TABLE memory_items DROP COLUMN IF EXISTS search_vector;")
