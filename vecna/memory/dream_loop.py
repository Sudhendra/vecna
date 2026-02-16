"""
Vecna Dream Loop - Memory Consolidation System

The dream loop runs periodically to:
1. Compress old episodic events into summarized episodes
2. Reinforce important memories (increase confidence)
3. Decay stale memories (decrease confidence or archive)
4. Generate new insights by cross-referencing memories
5. Update the identity timeline with significant changes

Inspired by how biological memory consolidation works during sleep.
"""

import logging
from typing import List, Dict, Optional, Any, TYPE_CHECKING
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import json

from vecna.memory.patterns import SessionPatternDetector

logger = logging.getLogger("vecna.memory.dream_loop")

if TYPE_CHECKING:
    from vecna.memory.pg_store import PgMemoryStore


@dataclass
class DreamResult:
    """Result of a dream loop iteration."""

    events_compressed: int = 0
    episodes_created: int = 0
    memories_reinforced: int = 0
    memories_decayed: int = 0
    insights_generated: int = 0
    duration_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "events_compressed": self.events_compressed,
            "episodes_created": self.episodes_created,
            "memories_reinforced": self.memories_reinforced,
            "memories_decayed": self.memories_decayed,
            "insights_generated": self.insights_generated,
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
            "timestamp": datetime.now().isoformat(),
        }


class DreamLoop:
    """
    Memory consolidation system for Vecna.

    Runs periodically (default: daily) to compress, reinforce, and
    consolidate memories in the substrate.
    """

    def __init__(
        self,
        pg_store: Optional["PgMemoryStore"] = None,
        compress_after_days: int = 7,
        decay_threshold_days: int = 30,
        reinforcement_threshold: float = 0.7,
        decay_rate: float = 0.1,
        min_confidence: float = 0.1,
        summarizer=None,  # Optional LLM for generating summaries
    ):
        """
        Initialize the dream loop.

        Args:
            pg_store: PostgreSQL memory store instance
            compress_after_days: Compress events older than this
            decay_threshold_days: Start decaying memories after this
            reinforcement_threshold: Reinforce memories with retrieval above this
            decay_rate: How much to decay confidence per cycle
            min_confidence: Minimum confidence before archiving
            summarizer: Optional callable for generating episode summaries
        """
        self.pg_store = pg_store
        self.compress_after_days = compress_after_days
        self.decay_threshold_days = decay_threshold_days
        self.reinforcement_threshold = reinforcement_threshold
        self.decay_rate = decay_rate
        self.min_confidence = min_confidence
        self.summarizer = summarizer

        self._last_run: Optional[datetime] = None

    def run(self, dry_run: bool = False) -> DreamResult:
        """
        Run one iteration of the dream loop.

        Args:
            dry_run: If True, don't actually modify the database

        Returns:
            DreamResult with statistics about what was processed
        """
        start_time = datetime.now()
        result = DreamResult()

        logger.info("Dream loop starting...")

        try:
            # Phase 1: Compress old events into episodes
            compressed, episodes = self._compress_events(dry_run)
            result.events_compressed = compressed
            result.episodes_created = episodes

            # Phase 2: Reinforce frequently-accessed memories
            reinforced = self._reinforce_memories(dry_run)
            result.memories_reinforced = reinforced

            # Phase 3: Decay stale memories
            decayed = self._decay_memories(dry_run)
            result.memories_decayed = decayed

            # Phase 4: Generate insights from recurring patterns and related memories
            insights = self._generate_insights(dry_run)
            result.insights_generated = insights

        except Exception as e:
            logger.error(f"Dream loop error: {e}")
            result.errors.append(str(e))

        result.duration_seconds = (datetime.now() - start_time).total_seconds()
        self._last_run = datetime.now()

        logger.info(
            f"Dream loop complete: {result.events_compressed} events compressed, "
            f"{result.episodes_created} episodes created, "
            f"{result.memories_reinforced} reinforced, "
            f"{result.memories_decayed} decayed, "
            f"took {result.duration_seconds:.2f}s"
        )

        # Record dream result as an event
        if not dry_run and self.pg_store:
            self._record_dream_event(result)

        return result

    def _compress_events(self, dry_run: bool) -> tuple:
        """Compress old events into summarized episodes."""
        if not self.pg_store:
            return 0, 0

        conn = self.pg_store._get_connection()
        cutoff = datetime.now() - timedelta(days=self.compress_after_days)

        events_compressed = 0
        episodes_created = 0

        try:
            with conn.cursor() as cur:
                # Get events older than cutoff that haven't been compressed
                cur.execute(
                    """
                    SELECT id, event_type, payload, session_id, created_at
                    FROM memory_events
                    WHERE created_at < %s
                    AND NOT EXISTS (
                        SELECT 1 FROM episodes e 
                        WHERE e.metadata->>'source_event_ids' LIKE '%%' || memory_events.id::text || '%%'
                    )
                    ORDER BY created_at
                    LIMIT 1000
                """,
                    (cutoff,),
                )

                rows = cur.fetchall()

                if not rows:
                    return 0, 0

                # Group events by session or by time windows
                event_groups = self._group_events_for_compression(rows)

                for group in event_groups:
                    if dry_run:
                        events_compressed += len(group)
                        episodes_created += 1
                        continue

                    # Create episode from group
                    episode = self._create_episode_from_events(group)
                    if episode:
                        from vecna.memory.pg_store import Episode

                        ep = Episode(
                            summary=episode["summary"],
                            start_time=episode["start_time"],
                            end_time=episode["end_time"],
                            event_count=len(group),
                            tags=episode.get("tags", []),
                            metadata={
                                "source_event_ids": [str(e[0]) for e in group],
                                "compressed_at": datetime.now().isoformat(),
                            },
                        )

                        # Embed the summary
                        if self.pg_store.embed:
                            embedding = self.pg_store.embed([ep.summary])[0]
                            ep.embedding = embedding.tolist()

                        episode_id = self.pg_store.add_episode(ep)

                        if episode_id:
                            episodes_created += 1
                            events_compressed += len(group)

                if not dry_run:
                    conn.commit()

        except Exception as e:
            logger.error(f"Event compression error: {e}")
            if not dry_run:
                conn.rollback()

        return events_compressed, episodes_created

    def _group_events_for_compression(self, rows: List) -> List[List]:
        """Group events by session or time window for compression."""
        if not rows:
            return []

        groups = []
        current_group = []
        last_session = None
        last_time = None

        # Group by session, or by 1-hour windows if no session
        for row in rows:
            event_id, event_type, payload, session_id, created_at = row

            if session_id:
                # Group by session
                if session_id != last_session and current_group:
                    groups.append(current_group)
                    current_group = []
                current_group.append(row)
                last_session = session_id
            else:
                # Group by time window (1 hour)
                if last_time and (created_at - last_time).total_seconds() > 3600:
                    if current_group:
                        groups.append(current_group)
                        current_group = []
                current_group.append(row)
                last_time = created_at

        if current_group:
            groups.append(current_group)

        return groups

    def _create_episode_from_events(self, events: List) -> Optional[Dict]:
        """Create an episode summary from a group of events."""
        if not events:
            return None

        # Extract event types and key information
        event_types = set()
        payloads = []

        for event_id, event_type, payload, session_id, created_at in events:
            event_types.add(event_type)
            if isinstance(payload, str):
                payload = json.loads(payload)
            payloads.append(payload)

        start_time = events[0][4]
        end_time = events[-1][4]

        # Generate summary
        if self.summarizer:
            # Use LLM to summarize
            summary = self._llm_summarize(events)
        else:
            # Simple rule-based summary
            summary = self._simple_summarize(event_types, payloads, len(events))

        # Extract tags
        tags = list(event_types)

        return {
            "summary": summary,
            "start_time": start_time,
            "end_time": end_time,
            "tags": tags,
        }

    def _simple_summarize(self, event_types: set, payloads: List, count: int) -> str:
        """Generate a simple rule-based summary."""
        types_str = ", ".join(sorted(event_types))

        # Extract key themes from payloads
        topics = set()
        for payload in payloads:
            if isinstance(payload, dict):
                if "domain" in payload:
                    topics.add(payload["domain"])
                if "topic" in payload:
                    topics.add(payload["topic"])

        topics_str = ", ".join(topics) if topics else "general activity"

        return f"Episode containing {count} events ({types_str}) related to {topics_str}"

    def _llm_summarize(self, events: List) -> str:
        """Use LLM to generate a summary (if summarizer is available)."""
        if not self.summarizer:
            return self._simple_summarize(set(), [], len(events))

        # Format events for LLM
        event_texts = []
        for event_id, event_type, payload, session_id, created_at in events[:20]:  # Limit
            if isinstance(payload, str):
                payload = json.loads(payload)
            event_texts.append(f"[{event_type}] {json.dumps(payload)[:200]}")

        prompt = f"""Summarize these {len(events)} events into a single coherent episode description.
Focus on the key actions, outcomes, and insights. Keep it under 200 words.

Events:
{chr(10).join(event_texts)}

Summary:"""

        try:
            return self.summarizer(prompt)
        except Exception as e:
            logger.error(f"LLM summarization failed: {e}")
            return self._simple_summarize(set(), [], len(events))

    def _reinforce_memories(self, dry_run: bool) -> int:
        """Reinforce frequently-accessed memories."""
        if not self.pg_store:
            return 0

        conn = self.pg_store._get_connection()
        reinforced = 0

        try:
            with conn.cursor() as cur:
                # Find frequently retrieved memories
                cur.execute(
                    """
                    SELECT id, confidence, retrieval_count
                    FROM memory_items
                    WHERE retrieval_count > 5
                    AND last_retrieved_at > %s
                    AND confidence < 0.95
                """,
                    (datetime.now() - timedelta(days=7),),
                )

                rows = cur.fetchall()

                for item_id, confidence, retrieval_count in rows:
                    # Calculate reinforcement boost
                    boost = min(0.1, retrieval_count * 0.01)
                    new_confidence = min(0.99, confidence + boost)

                    if dry_run:
                        reinforced += 1
                        continue

                    cur.execute(
                        """
                        UPDATE memory_items
                        SET confidence = %s, updated_at = %s
                        WHERE id = %s
                    """,
                        (new_confidence, datetime.now(), item_id),
                    )
                    reinforced += 1

                if not dry_run:
                    conn.commit()

        except Exception as e:
            logger.error(f"Memory reinforcement error: {e}")
            if not dry_run:
                conn.rollback()

        return reinforced

    def _decay_memories(self, dry_run: bool) -> int:
        """Decay stale memories that haven't been accessed."""
        if not self.pg_store:
            return 0

        conn = self.pg_store._get_connection()
        decayed = 0

        try:
            with conn.cursor() as cur:
                # Find stale memories
                cutoff = datetime.now() - timedelta(days=self.decay_threshold_days)

                cur.execute(
                    """
                    SELECT id, confidence
                    FROM memory_items
                    WHERE (last_retrieved_at IS NULL OR last_retrieved_at < %s)
                    AND updated_at < %s
                    AND confidence > %s
                    AND item_type NOT IN ('axiom', 'core_belief')
                """,
                    (cutoff, cutoff, self.min_confidence),
                )

                rows = cur.fetchall()

                for item_id, confidence in rows:
                    new_confidence = max(self.min_confidence, confidence - self.decay_rate)

                    if dry_run:
                        decayed += 1
                        continue

                    cur.execute(
                        """
                        UPDATE memory_items
                        SET confidence = %s, updated_at = %s
                        WHERE id = %s
                    """,
                        (new_confidence, datetime.now(), item_id),
                    )
                    decayed += 1

                if not dry_run:
                    conn.commit()

        except Exception as e:
            logger.error(f"Memory decay error: {e}")
            if not dry_run:
                conn.rollback()

        return decayed

    def _generate_insights(self, dry_run: bool) -> int:
        """Generate new insights by cross-referencing recurring themes and memories."""
        if not self.pg_store:
            return 0

        try:
            get_events = getattr(self.pg_store, "get_recent_events", None)
            if not callable(get_events):
                return 0

            events = get_events(limit=200)
            detector = SessionPatternDetector(
                min_count=2,
                max_patterns=5,
                exclude_event_types={"dream_loop"},
            )
            pattern_result = detector.detect(events)
            patterns = pattern_result.get("patterns", [])
            if not patterns:
                return 0

            generated = 0
            add_item = getattr(self.pg_store, "add_item", None)
            search = getattr(self.pg_store, "search", None)

            for pattern in patterns:
                theme = pattern.get("theme", "")
                if not theme:
                    continue

                related_count = 0
                if callable(search):
                    try:
                        related = search(theme, top_k=3)
                        related_count = len(related or [])
                    except Exception:
                        related_count = 0

                base_text = (
                    f"Recurring theme '{theme}' appears {pattern.get('count', 0)} times "
                    f"({pattern.get('frequency', 0):.2f} of recent events) with "
                    f"{related_count} related memories."
                )

                insight_text = base_text
                if self.summarizer:
                    prompt = f"Convert this memory signal into one concise insight: {base_text}"
                    try:
                        insight_text = self.summarizer(prompt)
                    except Exception as e:
                        logger.error(f"Insight summarization failed for theme '{theme}': {e}")

                if dry_run:
                    generated += 1
                    continue

                if not callable(add_item):
                    continue

                from vecna.memory.pg_store import MemoryItem

                item = MemoryItem(
                    content=str(insight_text),
                    item_type="hypothesis",
                    confidence=0.6,
                    domain="meta",
                    metadata={
                        "source": "dream_loop",
                        "theme": theme,
                        "pattern_count": pattern.get("count", 0),
                    },
                )
                add_result = add_item(item)
                if add_result:
                    generated += 1

            return generated
        except Exception as e:
            logger.error(f"Insight generation error: {e}")
            return 0

    def _record_dream_event(self, result: DreamResult) -> None:
        """Record the dream loop execution as an event."""
        if not self.pg_store:
            return

        try:
            from vecna.memory.pg_store import MemoryEvent

            event = MemoryEvent(
                event_type="dream_loop",
                payload=result.to_dict(),
            )
            self.pg_store.add_event(event)
        except Exception as e:
            logger.error(f"Failed to record dream event: {e}")


def run_dream_loop(
    connection_string: Optional[str] = None,
    compress_after_days: int = 7,
    decay_threshold_days: int = 30,
    dry_run: bool = False,
) -> DreamResult:
    """
    Convenience function to run the dream loop.

    Args:
        connection_string: PostgreSQL connection URL (or uses VECNA_PG_URL)
        compress_after_days: Compress events older than this
        decay_threshold_days: Start decaying memories after this
        dry_run: If True, don't actually modify the database

    Returns:
        DreamResult with statistics
    """
    from vecna.memory.pg_store import PgMemoryStore

    store = PgMemoryStore(connection_string=connection_string)

    dream = DreamLoop(
        pg_store=store,
        compress_after_days=compress_after_days,
        decay_threshold_days=decay_threshold_days,
    )

    try:
        result = dream.run(dry_run=dry_run)
    finally:
        store.close()

    return result


def run_scheduled_dream_loop(dry_run: bool = False) -> DreamResult:
    return run_dream_loop(dry_run=dry_run)
