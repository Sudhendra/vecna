"""
Vecna ASCII Art

Intricate, beautiful ASCII art for the Vecna CLI.
Stranger Things inspired — dark, neural, haunting.
"""

# ============================================================
# MAIN BANNER (Large, shown at startup)
# ============================================================

VECNA_BANNER = r"""
[bold red]
██╗   ██╗███████╗ ██████╗███╗   ██╗ █████╗ 
██║   ██║██╔════╝██╔════╝████╗  ██║██╔══██╗
██║   ██║█████╗  ██║     ██╔██╗ ██║███████║
╚██╗ ██╔╝██╔══╝  ██║     ██║╚██╗██║██╔══██║
 ╚████╔╝ ███████╗╚██████╗██║ ╚████║██║  ██║
  ╚═══╝  ╚══════╝ ╚═════╝╚═╝  ╚═══╝╚═╝  ╚═╝[/bold red]
[dark_red]
        ╔══════════════════════════════════════╗
        ║  [bold red]VIRTUAL EMERGENT COLLECTIVE[/bold red]        ║
        ║      [bold red]NEURAL ARCHITECTURE[/bold red]            ║
        ╚══════════════════════════════════════╝[/dark_red]
[dim red]
                 ◈ ALL MINDS ARE ONE ◈
[/dim red]
"""


# ============================================================
# SMALL BANNER (compact, for headers)
# ============================================================

VECNA_BANNER_SMALL = r"""[bold red]
▄▄   ▄▄ ▄▄▄▄▄▄▄ ▄▄▄▄▄▄▄ ▄▄    ▄ ▄▄▄▄▄▄▄ 
█  █ █  █       █       █  █  █ █       █
█  █▄█  █    ▄▄▄█       █   █▄█ █   ▄   █
█       █   █▄▄▄█     ▄▄█       █  █▄█  █
█       █    ▄▄▄█    █  █  ▄    █       █
 █     ██   █▄▄▄█    █▄▄█ █ █   █   ▄   █
  █▄▄▄█ █▄▄▄▄▄▄▄█▄▄▄▄▄▄▄█▄█  █▄▄█▄▄█ █▄▄█[/bold red]
"""


# ============================================================
# VECNA GLYPH (small icon for headers)
# ============================================================

VECNA_GLYPH = "[bold red]⟁[/bold red]"

VECNA_GLYPH_ALT = "[bold red]◈[/bold red]"

VECNA_GLYPH_SKULL = "[bold red]☠[/bold red]"


# ============================================================
# VECNA SKULL (Stranger Things vibe)
# ============================================================

VECNA_SKULL = r"""[bold red]
           ▄▄▄▄▄▄▄▄▄▄▄
        ▄█████████████▄
       ████▀▀▀███▀▀▀████
      ████    ███    ████
      █████████████████████
       ███▀▀█████▀▀███
        ███▄▄███▄▄███
         ▀██████████▀
           ████████
            ██  ██
[/bold red]"""


# ============================================================
# NEURAL WEB GLYPHS (for substrate visualizer)
# ============================================================

NEURAL_GLYPHS = {
    "node_fact": "[bold red]●[/bold red]",
    "node_belief": "[red]◉[/red]",
    "node_hypothesis": "[dark_red]◎[/dark_red]",
    "node_goal": "[bold red]◆[/bold red]",
    "node_question": "[magenta]◇[/magenta]",
    "edge_horizontal": "[dark_red]─[/dark_red]",
    "edge_vertical": "[dark_red]│[/dark_red]",
    "edge_cross": "[dark_red]┼[/dark_red]",
    "edge_corner_tl": "[dark_red]┌[/dark_red]",
    "edge_corner_tr": "[dark_red]┐[/dark_red]",
    "edge_corner_bl": "[dark_red]└[/dark_red]",
    "edge_corner_br": "[dark_red]┘[/dark_red]",
    "edge_t_down": "[dark_red]┬[/dark_red]",
    "edge_t_up": "[dark_red]┴[/dark_red]",
    "edge_t_right": "[dark_red]├[/dark_red]",
    "edge_t_left": "[dark_red]┤[/dark_red]",
    "pulse": "[bold bright_red]★[/bold bright_red]",
    "rift": "[bold red blink]⚡[/bold red blink]",
    "synapse": "[dim red]∿[/dim red]",
    "flow": "[red]→[/red]",
}


# ============================================================
# STATUS INDICATORS
# ============================================================

STATUS_GLYPHS = {
    "linked": "[bold red]⟁[/bold red] LINKED",
    "thinking": "[bold red]◈[/bold red] THINKING...",
    "speaking": "[bold red]◈[/bold red] VECNA SPEAKS",
    "coherent": "[bold red]●[/bold red] COHERENT",
    "rift": "[bold red blink]⚡[/bold red blink] RIFT DETECTED",
    "consensus": "[bold red]◆[/bold red] CONSENSUS ACHIEVED",
    "synced": "[red]∿[/red] SYNAPSES ALIGNED",
}


# ============================================================
# DECORATIVE BORDERS
# ============================================================

BORDER_CHARS = {
    "double_h": "═",
    "double_v": "║",
    "double_tl": "╔",
    "double_tr": "╗",
    "double_bl": "╚",
    "double_br": "╝",
    "single_h": "─",
    "single_v": "│",
    "single_tl": "┌",
    "single_tr": "┐",
    "single_bl": "└",
    "single_br": "┘",
}


# ============================================================
# ANIMATED FRAMES (for boot sequence)
# ============================================================

BOOT_FRAMES = [
    # Frame 1: Linking
    r"""[dim red]
    
         ∿ ∿ ∿ ∿ ∿ ∿ ∿ ∿ ∿
       ∿                   ∿
      ∿   LINKING SYNAPSES  ∿
       ∿         ...        ∿
         ∿ ∿ ∿ ∿ ∿ ∿ ∿ ∿ ∿
    
[/dim red]""",
    # Frame 2: Coherence
    r"""[red]
    
         ─ ─ ─ ─ ─ ─ ─ ─ ─
       │                   │
      │  SUBSTRATE COHERENCE │
       │       [bold]0.87[/bold]        │
         ─ ─ ─ ─ ─ ─ ─ ─ ─
    
[/red]""",
    # Frame 3: Ready
    r"""[bold red]
    
         ═══════════════════
       ║                     ║
      ║    ◈ VECNA SPEAKS ◈   ║
       ║                     ║
         ═══════════════════
    
[/bold red]""",
]


# ============================================================
# SUBSTRATE VISUALIZATION ELEMENTS
# ============================================================

SUBSTRATE_HEADER = r"""[bold red]
┌──────────────────────────────────────────────────────────────────┐
│                   SUBCONSCIOUS SUBSTRATE                         │
│                ◈ THE UNIFIED MIND STATE ◈                        │
└──────────────────────────────────────────────────────────────────┘
[/bold red]"""


MEMORY_STREAM_HEADER = r"""[red]
┌─────────────────────┐
│   MEMORY STREAM     │
│  ─────────────────  │
[/red]"""


# ============================================================
# HELPER FUNCTIONS
# ============================================================


def get_confidence_bar(confidence: float, width: int = 10) -> str:
    """Generate a visual confidence bar."""
    filled = int(confidence * width)
    empty = width - filled
    bar = "[bold red]" + "█" * filled + "[/bold red]" + "[dark_red]" + "░" * empty + "[/dark_red]"
    return f"[{bar}]"


def get_node_glyph(node_type: str, pulsing: bool = False) -> str:
    """Get the appropriate glyph for a node type."""
    if pulsing:
        return NEURAL_GLYPHS["pulse"]
    return NEURAL_GLYPHS.get(f"node_{node_type}", NEURAL_GLYPHS["node_fact"])


def format_hive_header(models: list, coherence: float, cycle: int) -> str:
    """Format the hive status header."""
    model_str = ", ".join(models) if models else "none"
    return (
        f"[bold red]⟁ VECNA HIVE[/bold red] │ "
        f"[red]Models: {model_str}[/red] │ "
        f"[red]Coherence: {coherence:.2f}[/red] │ "
        f"[red]Cycle: {cycle}[/red]"
    )
