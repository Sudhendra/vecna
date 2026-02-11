"""Add markdown and search metadata tables

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

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS markdown_chunks (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            source_file TEXT NOT NULL,
            line_start INTEGER NOT NULL,
            line_end INTEGER NOT NULL,
            heading_path TEXT NOT NULL,
            content TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            embedding vector(1536),
            search_vector tsvector GENERATED ALWAYS AS
                (to_tsvector('english', content)) STORED,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS markdown_chunks_source_hash_idx
        ON markdown_chunks (source_file, content_hash);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS markdown_chunks_source_idx
        ON markdown_chunks (source_file);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS markdown_chunks_search_idx
        ON markdown_chunks USING GIN (search_vector);
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS markdown_file_hashes (
            file_path TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            last_indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS markdown_file_hashes;")
    op.execute("DROP INDEX IF EXISTS markdown_chunks_source_hash_idx;")
    op.execute("DROP INDEX IF EXISTS markdown_chunks_search_idx;")
    op.execute("DROP INDEX IF EXISTS markdown_chunks_source_idx;")
    op.execute("DROP TABLE IF EXISTS markdown_chunks;")
    op.execute("DROP INDEX IF EXISTS memory_items_search_vector_idx;")
    op.execute("ALTER TABLE memory_items DROP COLUMN IF EXISTS search_vector;")
