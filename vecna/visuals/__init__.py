"""
Vecna CLI - Visuals Module

ASCII art, color themes, and boot animations for the Vecna hive mind interface.
Stranger Things red aesthetic throughout.
"""

from vecna.visuals.theme import VecnaTheme, VECNA_COLORS
from vecna.visuals.ascii_art import (
    VECNA_BANNER,
    VECNA_BANNER_SMALL,
    VECNA_GLYPH,
    VECNA_SKULL,
)
from vecna.visuals.boot import play_boot_sequence

__all__ = [
    "VecnaTheme",
    "VECNA_COLORS",
    "VECNA_BANNER",
    "VECNA_BANNER_SMALL",
    "VECNA_GLYPH",
    "VECNA_SKULL",
    "play_boot_sequence",
]
