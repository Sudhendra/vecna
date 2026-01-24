#!/usr/bin/env python3
"""
VECNA Demo: Continuous Hive Thinking

This demonstrates the hive mind in continuous mode, where it
keeps thinking and building knowledge over multiple cycles.

This is closer to a true "always-on" hive mind that accumulates
wisdom over time.

Storage: Uses PostgreSQL for persistent state and Redis for caching.
Set VECNA_PG_URL and VECNA_REDIS_URL environment variables.
"""

import asyncio
import os
from vecna import HiveMind
from vecna.orchestrator import HiveConfig


async def main():
    """
    Continuous thinking: the hive builds knowledge over time.
    """

    print("=" * 60)
    print("VECNA: Continuous Hive Mind")
    print("=" * 60)
    print()

    # Check storage configuration
    pg_url = os.getenv("VECNA_PG_URL")
    redis_url = os.getenv("VECNA_REDIS_URL")
    print("Storage Configuration:")
    print(f"  PostgreSQL: {'✓ configured' if pg_url else '✗ not set (VECNA_PG_URL)'}")
    print(f"  Redis: {'✓ configured' if redis_url else '✗ not set (VECNA_REDIS_URL)'}")
    print()

    # Configure for multi-cycle thinking with PG memory
    config = HiveConfig(
        use_routing=True,
        max_parallel_models=2,
        compress_every=2,
        max_cycles=5,  # Think for 5 cycles
        verbose=True,
        use_pg_memory=True,  # Use PostgreSQL for memory storage
        persist_identity_events=True,  # Track identity evolution
    )

    hive = HiveMind(config)

    # Add models
    # GitHub Copilot (primary provider)
    if os.getenv("GITHUB_TOKEN") or os.path.exists(
        os.path.expanduser("~/.config/github-copilot/hosts.json")
    ):
        hive.add_copilot(model="gpt-4.1", name="fast-thinker", domain="general")
        print("✓ Added GitHub Copilot (fast-thinker) to the hive")

    if os.getenv("GROQ_API_KEY"):
        hive.add_groq(model="llama-3.1-70b-versatile", name="rapid-thinker", domain="general")
        print("✓ Added Groq Llama (rapid-thinker) to the hive")

    # Optional: Add another Copilot model for diversity
    # hive.add_copilot(model="claude-sonnet", name="deep-thinker", domain="general")

    print()
    print("Hive assembled for continuous thinking.")
    print()

    # A research-style task that benefits from iterative thinking
    task = """
    Research question: What are the most promising approaches to achieving 
    artificial general intelligence (AGI)?
    
    Analyze from multiple angles:
    1. Scaling current architectures (transformers, etc.)
    2. Hybrid symbolic-neural approaches
    3. Brain-inspired architectures
    4. Emergent intelligence from multi-agent systems
    
    For each approach, assess:
    - Current progress
    - Key challenges
    - Timeline estimates
    - Required breakthroughs
    
    Build a comprehensive mental model of the AGI landscape.
    """

    print("RESEARCH TASK:")
    print("-" * 40)
    print(task)
    print("-" * 40)
    print()

    # Track state evolution
    cycle_states = []

    def on_cycle(response: str, state):
        """Called after each thinking cycle."""
        cycle_states.append(
            {
                "facts": len(state.facts),
                "beliefs": len(state.beliefs),
                "hypotheses": len(state.hypotheses),
            }
        )
        print(
            f"\n[Cycle {len(cycle_states)}] Facts: {len(state.facts)}, Beliefs: {len(state.beliefs)}"
        )

    print("Starting continuous thinking...")
    print("(The hive will think for multiple cycles, building knowledge)")
    print()

    # Run continuous thinking
    response = await hive.think(task)

    print()
    print("=" * 60)
    print("FINAL HIVE RESPONSE:")
    print("=" * 60)
    print(response)
    print()

    # Show knowledge accumulation
    state = hive.state
    print("=" * 60)
    print("ACCUMULATED KNOWLEDGE:")
    print("=" * 60)

    print(f"\nTotal facts: {len(state.facts)}")
    print(f"Total beliefs: {len(state.beliefs)}")
    print(f"Total hypotheses: {len(state.hypotheses)}")
    print(f"Open questions: {len(state.open_questions)}")

    print("\n--- HIGH CONFIDENCE FACTS ---")
    for fact in sorted(state.facts, key=lambda f: f.confidence, reverse=True)[:10]:
        print(f"[{fact.confidence:.2f}] {fact.content}")

    print("\n--- KEY BELIEFS ---")
    for belief in sorted(state.beliefs, key=lambda b: b.confidence, reverse=True)[:5]:
        print(f"[{belief.confidence:.2f}] {belief.content}")

    print("\n--- ACTIVE HYPOTHESES ---")
    for hyp in [h for h in state.hypotheses if h.status == "active"][:5]:
        print(f"[{hyp.confidence:.2f}] {hyp.content}")

    # Save the accumulated knowledge to PostgreSQL
    hive.save()  # Saves to PostgreSQL (primary storage)
    print("\nKnowledge saved to PostgreSQL")
    print("The hive's knowledge persists across sessions.")

    # Optionally export to file for backup
    # hive.save("agi_research_backup.json")


if __name__ == "__main__":
    asyncio.run(main())
