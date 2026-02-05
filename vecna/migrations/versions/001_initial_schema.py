"""Initial Vecna memory substrate schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2025-01-24

This migration creates the complete memory substrate for Vecna:
- hive_state: Primary HiveState persistence
- memory_items: Semantic memory with vector embeddings
- memory_edges: Graph structure for causal links
- memory_events: Episodic event stream (partitioned)
- episodes: Compressed episodic chunks
- memory_snapshots: Dream loop output
- identity_timeline: Identity evolution tracking
- training_exports: Dataset export metadata
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    # ============================================================
    # hive_state: Primary HiveState persistence
    # ============================================================
    op.execute("""
        CREATE TABLE hive_state (
            key TEXT PRIMARY KEY,
            state JSONB NOT NULL,
            version INTEGER NOT NULL DEFAULT 0,
            state_hash TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # ============================================================
    # memory_items: Unified semantic memory with vector embeddings
    # ============================================================
    op.execute("""
        CREATE TABLE memory_items (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            content TEXT NOT NULL,
            item_type TEXT NOT NULL,
            confidence FLOAT NOT NULL DEFAULT 0.5,
            domain TEXT DEFAULT 'general',
            source_model TEXT,
            embedding vector(1536),
            metadata JSONB DEFAULT '{}',
            retrieval_count INTEGER DEFAULT 0,
            last_retrieved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    # HNSW index for fast ANN search
    op.execute("""
        CREATE INDEX memory_items_embedding_idx ON memory_items 
        USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
    """)

    # Additional indexes
    op.execute("CREATE INDEX memory_items_metadata_idx ON memory_items USING GIN (metadata);")
    op.execute(
        "CREATE INDEX memory_items_type_confidence_idx ON memory_items (item_type, confidence DESC);"
    )
    op.execute("CREATE INDEX memory_items_domain_idx ON memory_items (domain);")
    op.execute("CREATE INDEX memory_items_created_idx ON memory_items (created_at DESC);")

    # ============================================================
    # memory_edges: Graph structure for causal links and contradictions
    # ============================================================
    op.execute("""
        CREATE TABLE memory_edges (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            source_id UUID NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
            target_id UUID NOT NULL REFERENCES memory_items(id) ON DELETE CASCADE,
            relation TEXT NOT NULL,
            weight FLOAT DEFAULT 1.0,
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            
            UNIQUE(source_id, target_id, relation)
        );
    """)

    op.execute("CREATE INDEX memory_edges_source_idx ON memory_edges (source_id);")
    op.execute("CREATE INDEX memory_edges_target_idx ON memory_edges (target_id);")
    op.execute("CREATE INDEX memory_edges_relation_idx ON memory_edges (relation);")

    # ============================================================
    # memory_events: Raw episodic event stream (partitioned by month)
    # ============================================================
    op.execute("""
        CREATE TABLE memory_events (
            id UUID DEFAULT uuid_generate_v4(),
            event_type TEXT NOT NULL,
            payload JSONB NOT NULL,
            session_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at);
    """)

    # Create partitions for 2025
    for month in range(1, 13):
        next_month = month + 1 if month < 12 else 1
        next_year = 2025 if month < 12 else 2026
        op.execute(f"""
            CREATE TABLE memory_events_2025_{month:02d} PARTITION OF memory_events
            FOR VALUES FROM ('2025-{month:02d}-01') TO ('{next_year}-{next_month:02d}-01');
        """)

    # Create partitions for 2026
    for month in range(1, 13):
        next_month = month + 1 if month < 12 else 1
        next_year = 2026 if month < 12 else 2027
        op.execute(f"""
            CREATE TABLE memory_events_2026_{month:02d} PARTITION OF memory_events
            FOR VALUES FROM ('2026-{month:02d}-01') TO ('{next_year}-{next_month:02d}-01');
        """)

    op.execute("CREATE INDEX memory_events_type_idx ON memory_events (event_type);")
    op.execute("CREATE INDEX memory_events_session_idx ON memory_events (session_id);")
    op.execute("CREATE INDEX memory_events_created_idx ON memory_events (created_at DESC);")

    # ============================================================
    # episodes: Compressed episodic chunks
    # ============================================================
    op.execute("""
        CREATE TABLE episodes (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            summary TEXT NOT NULL,
            embedding vector(1536),
            start_time TIMESTAMPTZ NOT NULL,
            end_time TIMESTAMPTZ NOT NULL,
            event_count INTEGER DEFAULT 0,
            tags TEXT[] DEFAULT '{}',
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    op.execute("""
        CREATE INDEX episodes_embedding_idx ON episodes 
        USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
    """)
    op.execute("CREATE INDEX episodes_time_idx ON episodes (start_time, end_time);")
    op.execute("CREATE INDEX episodes_tags_idx ON episodes USING GIN (tags);")

    # ============================================================
    # memory_snapshots: Dream loop output
    # ============================================================
    op.execute("""
        CREATE TABLE memory_snapshots (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            summary TEXT NOT NULL,
            embedding vector(1536),
            state_hash TEXT,
            snapshot_type TEXT DEFAULT 'dream',
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    op.execute("""
        CREATE INDEX memory_snapshots_embedding_idx ON memory_snapshots 
        USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
    """)
    op.execute("CREATE INDEX memory_snapshots_type_idx ON memory_snapshots (snapshot_type);")
    op.execute("CREATE INDEX memory_snapshots_created_idx ON memory_snapshots (created_at DESC);")

    # ============================================================
    # identity_timeline: Evolution of the hive's identity
    # ============================================================
    op.execute("""
        CREATE TABLE identity_timeline (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            event_type TEXT NOT NULL,
            description TEXT,
            old_value JSONB,
            new_value JSONB,
            trigger TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    op.execute("CREATE INDEX identity_timeline_type_idx ON identity_timeline (event_type);")
    op.execute("CREATE INDEX identity_timeline_created_idx ON identity_timeline (created_at DESC);")

    # ============================================================
    # training_exports: Dataset export metadata
    # ============================================================
    op.execute("""
        CREATE TABLE training_exports (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            export_path TEXT NOT NULL,
            format TEXT DEFAULT 'jsonl',
            record_count INTEGER,
            start_time TIMESTAMPTZ,
            end_time TIMESTAMPTZ,
            filters JSONB DEFAULT '{}',
            metadata JSONB DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
    """)

    op.execute("CREATE INDEX training_exports_created_idx ON training_exports (created_at DESC);")


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign keys)
    op.execute("DROP TABLE IF EXISTS training_exports;")
    op.execute("DROP TABLE IF EXISTS identity_timeline;")
    op.execute("DROP TABLE IF EXISTS memory_snapshots;")
    op.execute("DROP TABLE IF EXISTS episodes;")
    op.execute("DROP TABLE IF EXISTS memory_events;")
    op.execute("DROP TABLE IF EXISTS memory_edges;")
    op.execute("DROP TABLE IF EXISTS memory_items;")
    op.execute("DROP TABLE IF EXISTS hive_state;")

    # Note: We don't drop the extensions as they may be used by other applications
