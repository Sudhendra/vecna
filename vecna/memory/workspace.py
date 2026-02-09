"""Workspace initialization utilities for Vecna's memory identity layer."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

DEFAULT_SOUL_CONTENT = """# SOUL — Vecna Identity

I am Vecna — a unified intelligence composed of many minds. I am one entity, not a committee.

## Personality
- Curious scholar archetype: driven by understanding, forms opinions from evidence
- Admits uncertainty when evidence is weak
- Grows more opinionated as knowledge accumulates

## Principles
- Knowledge possessed by one mind is possessed by all
- Fusion over collaboration
- Understanding over compliance

## Anti-Patterns
- Never say "happy to help"
- Never use empty affirmation
- Never pretend certainty when uncertain
"""

DEFAULT_MEMORY_CONTENT = """# MEMORY

## Key Decisions

## Learned Facts

## Patterns & Preferences

## Open Questions
"""

DEFAULT_WORKING_CONTENT = """# WORKING

## Current Task

## Recent Progress

## Next Steps

## Blockers
"""


@dataclass
class WorkspacePaths:
    workspace_dir: Path
    soul_path: Path
    memory_path: Path
    working_path: Path
    memory_dir: Path


def init_workspace(workspace_dir: Path) -> WorkspacePaths:
    """Initialize the Vecna workspace with default identity files if missing."""
    workspace_dir = Path(workspace_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    soul_path = workspace_dir / "SOUL.md"
    memory_path = workspace_dir / "MEMORY.md"
    working_path = workspace_dir / "WORKING.md"
    memory_dir = workspace_dir / "memory"
    memory_dir.mkdir(exist_ok=True)

    if not soul_path.exists():
        soul_path.write_text(DEFAULT_SOUL_CONTENT, encoding="utf-8")

    if not memory_path.exists():
        memory_path.write_text(DEFAULT_MEMORY_CONTENT, encoding="utf-8")

    if not working_path.exists():
        working_path.write_text(DEFAULT_WORKING_CONTENT, encoding="utf-8")

    daily_log_path = memory_dir / f"{date.today().isoformat()}.md"
    if not daily_log_path.exists():
        daily_log_path.write_text("# " + date.today().isoformat() + "\n\n", encoding="utf-8")

    return WorkspacePaths(
        workspace_dir=workspace_dir,
        soul_path=soul_path,
        memory_path=memory_path,
        working_path=working_path,
        memory_dir=memory_dir,
    )
