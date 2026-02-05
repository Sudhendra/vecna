"""Add missing columns to identity_timeline and dedupe constraint to memory_items

Revision ID: 002_identity_timeline_columns
Revises: 001_initial_schema
Create Date: 2025-01-24

This migration adds:
- Additional columns to identity_timeline for complete identity event tracking
- Unique constraint on memory_items for content+item_type deduplication
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_identity_timeline_columns"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # Add missing columns to identity_timeline
    # ============================================================

    # Add coherence column (float, the coherence value at this event)
    op.execute("""
        ALTER TABLE identity_timeline 
        ADD COLUMN IF NOT EXISTS coherence FLOAT DEFAULT 0.5;
    """)

    # Add memory_density column (float, signal strength of substrate)
    op.execute("""
        ALTER TABLE identity_timeline 
        ADD COLUMN IF NOT EXISTS memory_density FLOAT DEFAULT 0.0;
    """)

    # Add contradictions column (integer, number of contradictions at this point)
    op.execute("""
        ALTER TABLE identity_timeline 
        ADD COLUMN IF NOT EXISTS contradictions INTEGER DEFAULT 0;
    """)

    # Add tone column (text, unified/mixed/fractured)
    op.execute("""
        ALTER TABLE identity_timeline 
        ADD COLUMN IF NOT EXISTS tone TEXT DEFAULT 'mixed';
    """)

    # Add domain_shift column (text, any domain shift that occurred)
    op.execute("""
        ALTER TABLE identity_timeline 
        ADD COLUMN IF NOT EXISTS domain_shift TEXT;
    """)

    # Add state_version column (integer, version of hive state at this event)
    op.execute("""
        ALTER TABLE identity_timeline 
        ADD COLUMN IF NOT EXISTS state_version INTEGER DEFAULT 0;
    """)

    # Add index on coherence for querying identity shifts
    op.execute("""
        CREATE INDEX IF NOT EXISTS identity_timeline_coherence_idx 
        ON identity_timeline (coherence);
    """)

    # Add index on tone for filtering by identity tone
    op.execute("""
        CREATE INDEX IF NOT EXISTS identity_timeline_tone_idx 
        ON identity_timeline (tone);
    """)

    # ============================================================
    # Add unique constraint for memory_items deduplication
    # ============================================================

    # Add unique constraint on content + item_type for deduplication
    # This allows ON CONFLICT upsert in add_from_state()
    op.execute("""
        ALTER TABLE memory_items 
        ADD CONSTRAINT memory_items_content_type_unique 
        UNIQUE (content, item_type);
    """)


def downgrade() -> None:
    # Remove memory_items constraint
    op.execute("""
        ALTER TABLE memory_items 
        DROP CONSTRAINT IF EXISTS memory_items_content_type_unique;
    """)

    # Remove identity_timeline indexes
    op.execute("DROP INDEX IF EXISTS identity_timeline_tone_idx;")
    op.execute("DROP INDEX IF EXISTS identity_timeline_coherence_idx;")

    # Remove identity_timeline columns
    op.execute("ALTER TABLE identity_timeline DROP COLUMN IF EXISTS state_version;")
    op.execute("ALTER TABLE identity_timeline DROP COLUMN IF EXISTS domain_shift;")
    op.execute("ALTER TABLE identity_timeline DROP COLUMN IF EXISTS tone;")
    op.execute("ALTER TABLE identity_timeline DROP COLUMN IF EXISTS contradictions;")
    op.execute("ALTER TABLE identity_timeline DROP COLUMN IF EXISTS memory_density;")
    op.execute("ALTER TABLE identity_timeline DROP COLUMN IF EXISTS coherence;")
