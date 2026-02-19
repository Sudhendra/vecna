"""Concurrency stress tests for shared mutable state.

Amendment 12: Verify data integrity under concurrent access for:
- HiveState (concurrent add_fact)
- MetricsCollector (concurrent record_*)
- HiveState beliefs (concurrent add_belief)

Uses asyncio.gather() with 50+ concurrent operations and asserts no data loss.

Amendment 9: No trivial assertions — assert specific counts and values.
Amendment 11: Tests use public interface only.
"""

import asyncio

from vecna.core.hive_state import HiveState
from vecna.core.types import Belief, Fact
from vecna.observability.dashboard import MetricsCollector


class TestConcurrentHiveState:
    """Amendment 12: Verify HiveState shared mutable state under concurrent access."""

    async def test_concurrent_add_fact_no_data_loss(self):
        """50 concurrent add_fact calls must not lose data.

        Each fact has unique content so deduplication won't merge them.
        """
        state = HiveState()
        facts = [
            Fact(
                content=f"unique concurrent fact number {i} with hash {i * 37}",
                confidence=0.5,
                source_model="test",
            )
            for i in range(50)
        ]
        await asyncio.gather(*(asyncio.to_thread(state.add_fact, f) for f in facts))
        # Each fact has unique content so all 50 should be added
        assert len(state.facts) == 50

    async def test_concurrent_add_belief_no_data_loss(self):
        """50 concurrent add_belief calls must not corrupt state."""
        state = HiveState()
        beliefs = [
            Belief(
                content=f"unique concurrent belief number {i} with hash {i * 41}",
                confidence=0.5,
                source_model="test",
            )
            for i in range(50)
        ]
        await asyncio.gather(*(asyncio.to_thread(state.add_belief, b) for b in beliefs))
        assert len(state.beliefs) == 50

    async def test_concurrent_mixed_mutations(self):
        """Concurrent facts AND beliefs added simultaneously don't corrupt state."""
        state = HiveState()
        facts = [
            Fact(
                content=f"mixed concurrent fact {i} unique-{i * 53}",
                confidence=0.6,
                source_model="test",
            )
            for i in range(25)
        ]
        beliefs = [
            Belief(
                content=f"mixed concurrent belief {i} unique-{i * 59}",
                confidence=0.6,
                source_model="test",
            )
            for i in range(25)
        ]
        tasks = [asyncio.to_thread(state.add_fact, f) for f in facts] + [
            asyncio.to_thread(state.add_belief, b) for b in beliefs
        ]
        await asyncio.gather(*tasks)
        assert len(state.facts) == 25
        assert len(state.beliefs) == 25


class TestConcurrentMetricsCollector:
    """Amendment 12: Verify MetricsCollector under concurrent access."""

    async def test_concurrent_record_token_usage(self):
        """50 concurrent token usage recordings must all be counted."""
        collector = MetricsCollector()
        await asyncio.gather(
            *(asyncio.to_thread(collector.record_token_usage, "test", 100, 50) for _ in range(50))
        )
        snapshot = collector.get_snapshot()
        # 50 recordings * (100 + 50) = 7500 total tokens
        assert snapshot.total_tokens == 7500

    async def test_concurrent_record_tool_execution(self):
        """50 concurrent tool execution recordings must all be counted."""
        collector = MetricsCollector()
        await asyncio.gather(
            *(asyncio.to_thread(collector.record_tool_execution, True, 10.0) for _ in range(50))
        )
        assert collector.tools.total_executions == 50
        assert collector.tools.successful == 50

    async def test_concurrent_record_consensus_merge(self):
        """50 concurrent consensus merge recordings preserve count."""
        collector = MetricsCollector()
        await asyncio.gather(
            *(
                asyncio.to_thread(collector.record_consensus_merge, 1, 0, 0, agreement_rate=0.5)
                for _ in range(50)
            )
        )
        assert collector.consensus.total_merges == 50

    async def test_concurrent_session_token_attribution(self):
        """Concurrent token recordings attributed to a session preserve total."""
        collector = MetricsCollector()
        collector.record_session_start("stress-sess")
        await asyncio.gather(
            *(
                asyncio.to_thread(
                    collector.record_token_usage,
                    "model-a",
                    100,
                    50,
                    "stress-sess",
                )
                for _ in range(50)
            )
        )
        report = collector.to_full_report()
        # 50 recordings * (100 + 50) = 7500 total tokens in session
        assert report["sessions"]["stress-sess"]["token_count"] == 7500
