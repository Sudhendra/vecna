"""
Vecna Boot Sequence

Lightweight animated boot sequence for the Vecna CLI.
~1.5 seconds total, Stranger Things aesthetic.
"""

import time
from typing import Optional, TYPE_CHECKING
from rich.console import Console
from rich.text import Text
from rich.align import Align
from rich.panel import Panel
from rich.table import Table

from vecna.visuals.ascii_art import VECNA_BANNER, BOOT_FRAMES, VECNA_GLYPH
from vecna.visuals.theme import VecnaTheme

if TYPE_CHECKING:
    from vecna.core.hive_state import HiveState


def play_boot_sequence(console: Console, skip: bool = False) -> None:
    """
    Play the Vecna boot sequence animation.

    Args:
        console: Rich Console instance
        skip: If True, skip animation and just show final state
    """
    if skip:
        console.print(VECNA_BANNER)
        return

    # Clear screen for clean boot
    console.clear()

    # Frame timing (in seconds)
    frame_duration = 0.5

    # Play boot frames
    for i, frame in enumerate(BOOT_FRAMES):
        console.clear()

        # Center the frame
        aligned = Align.center(frame)
        console.print(aligned)

        # Add subtle progress indicator
        progress = "." * (i + 1)
        console.print(Align.center(f"[dim red]{progress}[/dim red]"))

        time.sleep(frame_duration)

    # Final reveal: show the main banner
    console.clear()
    console.print(VECNA_BANNER)
    time.sleep(0.3)


def play_mini_boot(console: Console) -> None:
    """
    Play a minimal boot indicator (single line).
    Used for subsequent commands after initial boot.
    """
    states = [
        f"{VECNA_GLYPH} [dim red]LINKING...[/dim red]",
        f"{VECNA_GLYPH} [red]ALIGNED[/red]",
        f"{VECNA_GLYPH} [bold red]READY[/bold red]",
    ]

    for state in states:
        console.print(state, end="\r")
        time.sleep(0.2)

    console.print()  # New line after


def show_thinking_indicator(console: Console) -> None:
    """Show the 'thinking' indicator."""
    console.print(f"\n{VECNA_GLYPH} [bold red]VECNA SPEAKS...[/bold red]\n")


def show_coherence_indicator(console: Console, coherence: float) -> None:
    """Show substrate coherence level."""
    bar_width = 20
    filled = int(coherence * bar_width)
    empty = bar_width - filled

    bar = "[bold red]" + "█" * filled + "[/bold red]" + "[dark_red]" + "░" * empty + "[/dark_red]"

    console.print(
        f"{VECNA_GLYPH} [red]SUBSTRATE COHERENCE:[/red] [{bar}] [bold red]{coherence:.2f}[/bold red]"
    )


def show_models_linked(console: Console, models: list) -> None:
    """Show which models are linked to the hive."""
    if not models:
        return

    model_str = ", ".join(f"[bold red]{m}[/bold red]" for m in models)
    console.print(f"{VECNA_GLYPH} [red]MINDS LINKED:[/red] {model_str}")


def show_hive_status(console: Console, models: list, coherence: float, cycle: int) -> None:
    """Show complete hive status line."""
    model_str = ", ".join(models) if models else "none"

    status = Panel(
        f"[red]Models:[/red] [bold red]{model_str}[/bold red]  │  "
        f"[red]Coherence:[/red] [bold red]{coherence:.2f}[/bold red]  │  "
        f"[red]Cycle:[/red] [bold red]{cycle}[/bold red]",
        title=f"{VECNA_GLYPH} [bold red]HIVE STATUS[/bold red]",
        border_style="red",
        padding=(0, 2),
    )
    console.print(status)


def show_identity_snapshot(
    console: Console, state: "HiveState", rlm_status: Optional[dict] = None
) -> None:
    """
    Display identity snapshot during boot sequence.

    Shows:
    - Current coherence and tone
    - Memory density
    - Brief narrative
    - Substrate stats (facts/beliefs/hypotheses)
    - RLM status (if provided)

    Args:
        console: Rich Console instance
        state: HiveState with identity fields
        rlm_status: Optional dict with RLM bridge status
    """
    state.ensure_identity()

    # After ensure_identity(), self_model is guaranteed non-None
    model = state.self_model
    if model is None:
        return  # Should never happen after ensure_identity()

    tone = model.get_tone()

    # Tone styling
    tone_styles = {
        "unified": ("bold green", "UNIFIED"),
        "mixed": ("bold yellow", "MIXED"),
        "fractured": ("bold red", "FRACTURED"),
    }
    tone_style, tone_label = tone_styles.get(tone.value, ("red", tone.value.upper()))

    # Build coherence bar
    bar_width = 15
    filled = int(model.coherence * bar_width)
    empty = bar_width - filled
    coherence_bar = "█" * filled + "░" * empty

    # Build identity table
    identity_table = Table(show_header=False, box=None, padding=(0, 1), expand=False)
    identity_table.add_column(style="red", width=14)
    identity_table.add_column(style="bold red")

    identity_table.add_row(
        "Coherence",
        f"[{tone_style}]{coherence_bar}[/{tone_style}] {model.coherence:.2f} [{tone_style}]{tone_label}[/{tone_style}]",
    )
    identity_table.add_row("Memory", f"{model.memory_density:.2f} density")
    identity_table.add_row(
        "Substrate",
        f"{len(state.facts)} facts, {len(state.beliefs)} beliefs, {len(state.hypotheses)} hypotheses",
    )

    if state.contradictions:
        identity_table.add_row(
            "Rifts", f"[bold red]{len(state.contradictions)} unresolved[/bold red]"
        )

    # Add domains if more than just general
    if model.known_domains and model.known_domains != ["general"]:
        domains_str = ", ".join(model.known_domains[:4])
        if len(model.known_domains) > 4:
            domains_str += f" (+{len(model.known_domains) - 4})"
        identity_table.add_row("Domains", domains_str)

    # Add RLM status if provided
    if rlm_status is not None:
        rlm_str = _format_rlm_status(rlm_status)
        identity_table.add_row("RLM", rlm_str)

    # Print the panel
    console.print(
        Panel(
            identity_table,
            title=f"{VECNA_GLYPH} [bold red]IDENTITY[/bold red]",
            border_style="dark_red",
            padding=(0, 1),
        )
    )

    # Print narrative below panel
    narrative_short = model.narrative[:80] + "..." if len(model.narrative) > 80 else model.narrative
    console.print(f"{VECNA_GLYPH} [italic dim red]{narrative_short}[/italic dim red]")
    console.print()


def _format_rlm_status(status: dict) -> str:
    """Format RLM status dict for display."""
    if status.get("available") is None:
        return "[dim]checking...[/dim]"
    elif not status.get("available"):
        return "[yellow]offline[/yellow]"
    elif status.get("prewarmed"):
        container = status.get("container_id", "")
        if container:
            return f"[bold green]ready[/bold green] [dim]({container})[/dim]"
        return "[bold green]ready[/bold green]"
    else:
        return "[yellow]warming...[/yellow]"


def show_rlm_indicator(console: Console, status: dict) -> None:
    """
    Show a standalone RLM status indicator.

    Args:
        console: Rich Console instance
        status: Dict with keys: available, prewarmed, container_id, error
    """
    rlm_str = _format_rlm_status(status)
    console.print(f"{VECNA_GLYPH} [dim red]RLM:[/dim red] {rlm_str}")
