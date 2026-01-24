"""
Vecna Theme - Stranger Things Red Aesthetic

Color palette and Rich styles for the Vecna CLI.
Deep blacks, blood reds, crimson accents, and faint purple glows.
"""

from rich.style import Style
from rich.theme import Theme


# ============================================================
# COLOR PALETTE (Stranger Things / Vecna Red)
# ============================================================

VECNA_COLORS = {
    # Primary
    "black": "#000000",
    "blood_red": "#8B0000",
    "crimson": "#DC143C",
    "bright_red": "#CC0000",
    # Secondary
    "dark_maroon": "#4A0000",
    "deep_red": "#660000",
    "wine": "#722F37",
    # Accent
    "purple_glow": "#4B0082",
    "dark_purple": "#2D0047",
    "violet": "#8B008B",
    # Alerts
    "warning_red": "#FF0000",
    "pulse_red": "#FF3333",
    # Text
    "dim_red": "#993333",
    "pale_red": "#CC6666",
    "white": "#FFFFFF",
    "gray": "#666666",
}


# ============================================================
# RICH STYLES
# ============================================================

VECNA_STYLES = {
    # Banners and headers
    "banner": Style(color=VECNA_COLORS["crimson"], bold=True),
    "header": Style(color=VECNA_COLORS["bright_red"], bold=True),
    "subheader": Style(color=VECNA_COLORS["blood_red"]),
    # Text
    "text": Style(color=VECNA_COLORS["pale_red"]),
    "dim": Style(color=VECNA_COLORS["dim_red"]),
    "muted": Style(color=VECNA_COLORS["deep_red"]),
    # Highlights
    "highlight": Style(color=VECNA_COLORS["crimson"], bold=True),
    "accent": Style(color=VECNA_COLORS["purple_glow"]),
    "glow": Style(color=VECNA_COLORS["violet"]),
    # Status
    "success": Style(color=VECNA_COLORS["crimson"]),
    "warning": Style(color=VECNA_COLORS["warning_red"], bold=True),
    "error": Style(color=VECNA_COLORS["pulse_red"], bold=True, blink=True),
    # Data types
    "fact": Style(color=VECNA_COLORS["bright_red"]),
    "belief": Style(color=VECNA_COLORS["blood_red"]),
    "hypothesis": Style(color=VECNA_COLORS["purple_glow"]),
    "contradiction": Style(color=VECNA_COLORS["warning_red"], bold=True),
    "question": Style(color=VECNA_COLORS["violet"]),
    "goal": Style(color=VECNA_COLORS["crimson"], bold=True),
    # Confidence levels
    "conf_high": Style(color=VECNA_COLORS["bright_red"], bold=True),
    "conf_medium": Style(color=VECNA_COLORS["blood_red"]),
    "conf_low": Style(color=VECNA_COLORS["dim_red"]),
    # Model sources
    "model": Style(color=VECNA_COLORS["purple_glow"], italic=True),
    # Borders and structure
    "border": Style(color=VECNA_COLORS["dark_maroon"]),
    "panel": Style(color=VECNA_COLORS["blood_red"]),
}


# ============================================================
# RICH THEME
# ============================================================

VECNA_THEME = Theme(
    {
        "vecna.banner": VECNA_STYLES["banner"],
        "vecna.header": VECNA_STYLES["header"],
        "vecna.subheader": VECNA_STYLES["subheader"],
        "vecna.text": VECNA_STYLES["text"],
        "vecna.dim": VECNA_STYLES["dim"],
        "vecna.muted": VECNA_STYLES["muted"],
        "vecna.highlight": VECNA_STYLES["highlight"],
        "vecna.accent": VECNA_STYLES["accent"],
        "vecna.glow": VECNA_STYLES["glow"],
        "vecna.success": VECNA_STYLES["success"],
        "vecna.warning": VECNA_STYLES["warning"],
        "vecna.error": VECNA_STYLES["error"],
        "vecna.fact": VECNA_STYLES["fact"],
        "vecna.belief": VECNA_STYLES["belief"],
        "vecna.hypothesis": VECNA_STYLES["hypothesis"],
        "vecna.contradiction": VECNA_STYLES["contradiction"],
        "vecna.question": VECNA_STYLES["question"],
        "vecna.goal": VECNA_STYLES["goal"],
        "vecna.model": VECNA_STYLES["model"],
        "vecna.border": VECNA_STYLES["border"],
        "vecna.panel": VECNA_STYLES["panel"],
    }
)


# ============================================================
# VECNA THEME CLASS
# ============================================================


# ============================================================
# STYLES ALIAS (for visualizer compatibility)
# ============================================================

STYLES = {
    "primary": VECNA_STYLES["banner"],
    "secondary": VECNA_STYLES["text"],
    "accent": VECNA_STYLES["accent"],
    "glow": VECNA_STYLES["glow"],
    "dim": VECNA_STYLES["dim"],
    "warning": VECNA_STYLES["warning"],
}


class VecnaTheme:
    """
    Centralized theme access for Vecna CLI.
    """

    colors = VECNA_COLORS
    styles = VECNA_STYLES
    theme = VECNA_THEME

    @classmethod
    def get_style(cls, name: str) -> Style:
        """Get a style by name."""
        return cls.styles.get(name, Style())

    @classmethod
    def get_color(cls, name: str) -> str:
        """Get a color by name."""
        return cls.colors.get(name, "#FFFFFF")

    @classmethod
    def confidence_style(cls, confidence: float) -> Style:
        """Get style based on confidence level."""
        if confidence >= 0.8:
            return cls.styles["conf_high"]
        elif confidence >= 0.5:
            return cls.styles["conf_medium"]
        else:
            return cls.styles["conf_low"]

    @classmethod
    def type_style(cls, item_type: str) -> Style:
        """Get style based on item type."""
        type_map = {
            "fact": cls.styles["fact"],
            "belief": cls.styles["belief"],
            "hypothesis": cls.styles["hypothesis"],
            "contradiction": cls.styles["contradiction"],
            "question": cls.styles["question"],
            "goal": cls.styles["goal"],
        }
        return type_map.get(item_type, cls.styles["text"])
