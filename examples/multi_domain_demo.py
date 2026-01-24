#!/usr/bin/env python3
"""
VECNA Demo: Multi-Domain Expert Hive

This demonstrates the power of domain-specialized experts working
together in a hive mind to solve complex interdisciplinary problems.

The hive routes problems to the right experts while maintaining
a unified mental state.

Storage: Uses PostgreSQL for persistent state and Redis for caching.
Set VECNA_PG_URL and VECNA_REDIS_URL environment variables.
"""

import asyncio
import os
from vecna import HiveMind
from vecna.orchestrator import HiveConfig


async def main():
    """
    Multi-domain hive: specialists that think as one.
    """

    print("=" * 60)
    print("VECNA: Multi-Domain Expert Hive")
    print("=" * 60)
    print()

    # Configure for domain routing with PG memory
    config = HiveConfig(
        use_routing=True,
        max_parallel_models=3,
        compress_every=3,
        verbose=True,
        use_pg_memory=True,
    )

    # Create the hive
    hive = HiveMind(config)

    # Add domain-specialized models
    # Each model is tagged with its domain of expertise
    # Using GitHub Copilot as the primary provider

    if os.getenv("GITHUB_TOKEN") or os.path.exists(
        os.path.expanduser("~/.config/github-copilot/hosts.json")
    ):
        # Copilot GPT-4.1 as general reasoner
        hive.add_copilot(model="gpt-4.1", name="reasoner", domain="general")
        # Copilot GPT-4.1 as code expert
        hive.add_copilot(model="gpt-4.1", name="coder", domain="code")
        # Copilot Claude as science expert
        hive.add_copilot(model="claude-sonnet", name="scientist", domain="science")
        print("✓ Added Copilot experts (reasoner, coder, scientist)")

    if os.getenv("GROQ_API_KEY"):
        # Groq Llama as math expert (fast for calculations)
        hive.add_groq(model="llama-3.1-70b-versatile", name="mathematician", domain="math")
        print("✓ Added Groq expert (mathematician)")

    print()
    print("Domain experts assembled into unified hive.")
    print()

    # A complex interdisciplinary task
    task = """
    I'm building a quantum-resistant cryptocurrency. Help me with:
    
    1. CRYPTOGRAPHY: What post-quantum algorithms should I use for:
       - Key exchange (replace ECDH)
       - Digital signatures (replace ECDSA)
       - Hash functions
    
    2. IMPLEMENTATION: Sketch Python code for a basic post-quantum signature scheme.
    
    3. MATHEMATICS: Explain the lattice problems that make these schemes secure.
    
    4. ANALYSIS: What are the trade-offs vs classical cryptography?
       - Key sizes
       - Computation speed
       - Security assumptions
    
    Give me a comprehensive answer that I could use to start prototyping.
    """

    print("INTERDISCIPLINARY TASK:")
    print("-" * 40)
    print(task)
    print("-" * 40)
    print()
    print("The Hive is consulting experts...")
    print()

    # Think
    response = await hive.think(task)

    print()
    print("UNIFIED HIVE RESPONSE:")
    print("=" * 60)
    print(response)
    print("=" * 60)
    print()

    # Show what the hive learned
    state = hive.state

    print("HIVE KNOWLEDGE STATE:")
    print("-" * 40)

    print("\nTop Facts Learned:")
    for fact in sorted(state.facts, key=lambda f: f.confidence, reverse=True)[:5]:
        print(f"  [{fact.confidence:.1f}] {fact.content[:80]}...")

    print("\nKey Beliefs Formed:")
    for belief in sorted(state.beliefs, key=lambda b: b.confidence, reverse=True)[:3]:
        print(f"  [{belief.confidence:.1f}] {belief.content[:80]}...")

    print("\nOpen Questions:")
    for q in state.open_questions[:3]:
        print(f"  ? {q.question}")

    if state.contradictions:
        print("\nContradictions Found:")
        for c in state.contradictions[:2]:
            print(f"  ! {c.item_a_content[:40]} vs {c.item_b_content[:40]}")

    # Save to PostgreSQL
    hive.save()
    print("\nKnowledge saved to PostgreSQL")


if __name__ == "__main__":
    asyncio.run(main())
