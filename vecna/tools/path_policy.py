"""Filesystem path policy helpers for sandboxed tool access."""

from pathlib import Path
from typing import Any, List


def normalize_roots(roots: Any) -> List[Path]:
    """Expand and resolve configured root paths."""
    normalized: List[Path] = []

    if roots is None or isinstance(roots, (str, bytes)):
        return normalized

    try:
        root_values = iter(roots)
    except TypeError:
        return normalized

    for root in root_values:
        if not str(root).strip():
            continue
        try:
            normalized.append(Path(root).expanduser().resolve())
        except (OSError, TypeError, ValueError):
            continue
    return normalized


def is_allowed(path: str, roots: Any) -> bool:
    """Return True when path is at or below any allowed root."""
    if not str(path).strip():
        return False

    try:
        target = Path(path).expanduser().resolve()
    except OSError:
        return False

    for root in normalize_roots(roots):
        if target == root or root in target.parents:
            return True
    return False
