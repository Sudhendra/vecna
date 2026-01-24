#!/usr/bin/env python3
"""
VECNA Demo: Quick Start

Minimal example to get started with the hive mind.

Storage: Uses PostgreSQL for persistent state.
Set VECNA_PG_URL environment variable for persistence.
"""

import asyncio
import os
from vecna import HiveMind


async def main():
    # Create hive
    hive = HiveMind()

    # Add at least one model (uncomment what you have)

    # Option 1: GitHub Copilot (primary provider)
    if os.getenv("GITHUB_TOKEN") or os.path.exists(
        os.path.expanduser("~/.config/github-copilot/hosts.json")
    ):
        hive.add_copilot("gpt-4.1")

    # Option 2: Groq (free tier available)
    elif os.getenv("GROQ_API_KEY"):
        hive.add_groq("llama-3.1-70b-versatile")

    # Option 3: Local Ollama
    else:
        print("No API keys found. Trying local Ollama...")
        hive.add_ollama("llama3.1")

    # Ask the hive something
    response = await hive.think("What is the meaning of consciousness?")
    print(response)

    # State is automatically saved to PostgreSQL if VECNA_PG_URL is set


if __name__ == "__main__":
    asyncio.run(main())
