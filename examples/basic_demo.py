#!/usr/bin/env python3
"""
VECNA Demo: Basic Hive Mind Usage

This demonstrates how to create a hive mind with multiple AI models
and have them think together as ONE unified intelligence.

Storage: Uses PostgreSQL for persistent state and Redis for caching.
Set VECNA_PG_URL and VECNA_REDIS_URL environment variables.
"""

import asyncio
import os
from vecna import HiveMind


async def main():
    """
    Basic demo: Create a hive mind with multiple models.

    The hive will think about a complex task that benefits from
    multiple perspectives (code + reasoning + creativity).
    """

    print("=" * 60)
    print("VECNA: Virtual Emergent Collective Neural Architecture")
    print("=" * 60)
    print()

    # Check storage configuration
    pg_url = os.getenv("VECNA_PG_URL")
    redis_url = os.getenv("VECNA_REDIS_URL")
    print("Storage Configuration:")
    print(f"  PostgreSQL: {'✓ configured' if pg_url else '✗ not set (VECNA_PG_URL)'}")
    print(f"  Redis: {'✓ configured' if redis_url else '✗ not set (VECNA_REDIS_URL)'}")
    print()

    # Create the hive mind
    hive = HiveMind()

    # Add models to the hive
    # GitHub Copilot (primary provider)
    if os.getenv("GITHUB_TOKEN") or os.path.exists(
        os.path.expanduser("~/.config/github-copilot/hosts.json")
    ):
        hive.add_copilot(model="gpt-4.1", name="copilot-gpt4", domain="general")
        print("✓ Added GitHub Copilot (GPT-4.1) to the hive")

    # Groq (fast inference)
    if os.getenv("GROQ_API_KEY"):
        hive.add_groq(model="llama-3.1-70b-versatile", name="groq-llama", domain="general")
        print("✓ Added Groq Llama to the hive")

    # Local Ollama models (if running)
    # hive.add_ollama(model="llama3.1", name="local-llama", domain="general")

    print()
    print("Hive assembled. All minds are now ONE.")
    print()

    # The task
    task = """
    Design a system for detecting early signs of Alzheimer's disease using:
    1. Machine learning on brain MRI scans
    2. Natural language analysis of patient speech patterns
    3. Behavioral data from smartphone sensors
    
    Provide:
    - Architecture overview
    - Key algorithms for each modality
    - How to fuse the multimodal signals
    - Ethical considerations
    """

    print("TASK:")
    print("-" * 40)
    print(task)
    print("-" * 40)
    print()
    print("The Hive is thinking...")
    print()

    # Have the hive think
    response = await hive.think(task)

    print("HIVE RESPONSE:")
    print("=" * 60)
    print(response)
    print("=" * 60)
    print()

    # Show the hive state
    state = hive.state
    print(f"Hive State:")
    print(f"  - Facts learned: {len(state.facts)}")
    print(f"  - Beliefs formed: {len(state.beliefs)}")
    print(f"  - Hypotheses: {len(state.hypotheses)}")
    print(f"  - Open questions: {len(state.open_questions)}")
    print(f"  - Contradictions: {len(state.contradictions)}")

    # Save state to PostgreSQL (primary) or export to file (backup)
    hive.save()  # Saves to PostgreSQL
    print()
    print("State saved to PostgreSQL")

    # Optionally export to file for backup/debugging
    # hive.save("hive_state_backup.json")
    # print("State exported to hive_state_backup.json")


if __name__ == "__main__":
    asyncio.run(main())
