"""
Vecna CLI - Main Entry Point

The command-line interface for the Vecna hive mind.
All minds become one.
"""

import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from vecna.core.state_store import PostgresStore, get_default_manager, get_default_store
from vecna.tools.approvals import ApprovalStore
from vecna.visuals.ascii_art import VECNA_BANNER, VECNA_GLYPH
from vecna.visuals.boot import (
    play_boot_sequence,
    show_coherence_indicator,
    show_identity_snapshot,
    show_models_linked,
    show_thinking_indicator,
)
from vecna.visuals.theme import VECNA_THEME

load_dotenv()

console = Console(theme=VECNA_THEME)

# Config file path (state is stored in PostgreSQL)
CONFIG_FILE = Path.home() / ".vecna" / "config.json"


# Track if boot has played this session
_boot_played = False

# RLM prewarm task
_rlm_prewarm_task = None
_rlm_status = {"available": None, "prewarmed": False, "container_id": None, "error": None}


def _get_rlm_status() -> dict:
    """Get current RLM bridge status."""
    global _rlm_status
    try:
        from vecna.memory.rlm_bridge import get_rlm_bridge

        bridge = get_rlm_bridge()
        _rlm_status["available"] = bridge.is_docker_available()
        _rlm_status["prewarmed"] = bridge._prewarmed
        _rlm_status["container_id"] = bridge._container_id[:12] if bridge._container_id else None
    except ImportError:
        _rlm_status["available"] = False
        _rlm_status["error"] = "RLM bridge not installed"
    except Exception as e:
        _rlm_status["error"] = str(e)

    return _rlm_status


def _shutdown_rlm():
    """Shutdown RLM bridge and cleanup Docker container."""
    try:
        from vecna.memory.rlm_bridge import get_rlm_bridge
        import asyncio

        bridge = get_rlm_bridge()
        if bridge._container_id:
            # Run shutdown synchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(bridge.shutdown())
            loop.close()
    except ImportError:
        pass  # RLM bridge not available
    except Exception:
        pass  # Fail silently on cleanup


def _flush_offline_spool():
    """Flush any pending offline spool entries to PostgreSQL on exit."""
    try:
        manager = get_default_manager()
        status = manager.get_status()
        pending = status.get("offline_pending_count", 0)

        if pending > 0:
            logging.getLogger("vecna.cli").info(f"Flushing {pending} pending offline entries...")
            results = manager.flush_offline_spool()
            if results.get("flushed", 0) > 0:
                logging.getLogger("vecna.cli").info(
                    f"Flushed {results['flushed']} entries to PostgreSQL"
                )
    except Exception as e:
        logging.getLogger("vecna.cli").warning(f"Failed to flush offline spool: {e}")


def _prewarm_rlm_async():
    """Prewarm RLM bridge in background (non-blocking)."""
    global _rlm_prewarm_task, _rlm_status

    try:
        from vecna.memory.rlm_bridge import get_rlm_bridge

        bridge = get_rlm_bridge()
        _rlm_status["available"] = bridge.is_docker_available()

        if not bridge.is_docker_available():
            _rlm_status["error"] = "Docker not available"
            return  # Skip silently if Docker not available

        # Run prewarm in background
        import threading

        def prewarm():
            import asyncio

            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(bridge.prewarm())
                if result:
                    _rlm_status["prewarmed"] = True
                    _rlm_status["container_id"] = (
                        bridge._container_id[:12] if bridge._container_id else None
                    )
                else:
                    _rlm_status["error"] = "Prewarm failed"
            except Exception as e:
                _rlm_status["error"] = str(e)

        thread = threading.Thread(target=prewarm, daemon=True)
        thread.start()
        _rlm_prewarm_task = thread

    except ImportError:
        _rlm_status["available"] = False
        _rlm_status["error"] = "RLM bridge not installed"


def ensure_vecna_dir():
    """Ensure ~/.vecna directory exists."""
    vecna_dir = Path.home() / ".vecna"
    vecna_dir.mkdir(exist_ok=True)
    return vecna_dir


def _save_state(hive):
    """Save hive state to PostgreSQL store via PgStateManager."""
    try:
        manager = get_default_manager()
        manager.save_state(hive.state, "default")
    except Exception as e:
        logging.getLogger("vecna.cli").warning(f"Failed to save state: {e}")


def get_hive(use_config: bool = True):
    """
    Get or create the HiveMind instance.

    Args:
        use_config: If True, use ~/.vecna/config.json for model configuration.
                   If False, fall back to environment variable based setup.
    """
    from vecna import HiveMind
    from vecna.orchestrator import HiveConfig

    # Try config-based loading first
    if use_config:
        try:
            from vecna.config import ensure_default_config, create_adapters_from_config

            # Ensure config exists
            vecna_config = ensure_default_config()

            # Create HiveConfig from vecna config
            hive_config = HiveConfig(
                use_routing=vecna_config.use_routing,
                max_parallel_models=vecna_config.max_parallel_models,
                verbose=False,  # We handle output ourselves
                use_local_embeddings=False,
                auto_execute_code=vecna_config.auto_execute_code,
                use_pg_memory=True,  # Use PgStateManager
                persist_identity_events=True,  # Persist identity events to PG
            )

            hive = HiveMind(hive_config)

            # Create adapters from config
            adapters = create_adapters_from_config(vecna_config)
            for adapter in adapters:
                hive.loop.add_adapter(adapter)

            # Load existing state from PostgreSQL via PgStateManager
            try:
                manager = get_default_manager()
                state = manager.load_state("default")
                if state is not None:
                    hive.loop.state = state
            except Exception:
                pass  # Start fresh if load fails

            return hive

        except ImportError:
            # Config module not available, fall back to legacy
            pass
        except Exception as e:
            # Log error but continue with fallback
            import logging

            logging.getLogger("vecna.cli").warning(f"Config loading failed: {e}, using fallback")

    # Fallback: Legacy environment-based model loading
    hive_config = HiveConfig(
        use_routing=False,
        max_parallel_models=5,
        verbose=False,
        use_local_embeddings=False,
        use_pg_memory=True,  # Use PgStateManager
        persist_identity_events=True,  # Persist identity events to PG
    )

    hive = HiveMind(hive_config)

    # Models are loaded from config via Copilot authentication
    # No need to manually add models here - they're added via create_adapters_from_config

    if os.getenv("GROQ_API_KEY"):
        hive.add_groq(model="llama-3.1-70b-versatile", name="groq-llama", domain="general")

    # Load existing state from PostgreSQL via PgStateManager
    try:
        manager = get_default_manager()
        state = manager.load_state("default")
        if state is not None:
            hive.loop.state = state
    except Exception:
        pass  # Start fresh if load fails

    return hive


# ============================================================
# CHAT LOOP
# ============================================================


def _show_mini_help_panel():
    """Show a mini help panel with available commands."""
    help_table = Table(show_header=False, box=None, padding=(0, 2))
    help_table.add_column(style="bold red", width=12)
    help_table.add_column(style="dim red")

    help_table.add_row("state", "Show substrate status + RLM")
    help_table.add_row("status", "Full system diagnostics")
    help_table.add_row("identity", "Show identity (also: whoami)")
    help_table.add_row("memory", "Browse hive memory (memory fact|belief|hypothesis)")
    help_table.add_row("trace", "Show model contributions")
    help_table.add_row("execlog", "Show code execution history")
    help_table.add_row("persona", "Show/set persona (persona [name])")
    help_table.add_row("group", "Show/set group (group [name])")
    help_table.add_row("visualize", "Launch live substrate visualizer")
    help_table.add_row("reset", "Clear all memories")
    help_table.add_row("help", "Show this help")
    help_table.add_row("exit", "Exit chat (also: quit, :q, Ctrl+C)")

    console.print(
        Panel(
            help_table,
            title=f"{VECNA_GLYPH} [bold red]COMMANDS[/bold red]",
            border_style="dark_red",
            padding=(0, 1),
        )
    )
    console.print()


def _show_inline_memory(hive, item_type: str = "all", limit: int = 20):
    """Show semantic memory inline during chat."""
    state = hive.state

    console.print(f"\n{VECNA_GLYPH} [bold red]HIVE MEMORY[/bold red]\n")

    items = []

    if item_type in ["fact", "all"]:
        for f in state.facts:
            items.append(("fact", f.confidence, f.content, f.source_model))

    if item_type in ["belief", "all"]:
        for b in state.beliefs:
            items.append(("belief", b.confidence, b.content, b.source_model))

    if item_type in ["hypothesis", "all"]:
        for h in state.hypotheses:
            items.append(("hypothesis", h.confidence, h.content, h.source_model))

    # Sort by confidence
    items.sort(key=lambda x: x[1], reverse=True)
    items = items[:limit]

    if not items:
        console.print("[dim red]No memories found.[/dim red]\n")
        return

    table = Table(show_header=True, box=None, padding=(0, 1))
    table.add_column("Type", style="red", width=10)
    table.add_column("Conf", style="bold red", width=6)
    table.add_column("Content", style="red")
    table.add_column("Source", style="dim red", width=10)

    for itype, conf, content, source in items:
        content_short = content[:50] + "..." if len(content) > 50 else content
        table.add_row(itype, f"{conf:.2f}", content_short, source or "-")

    console.print(table)
    console.print()


def _show_inline_trace(hive):
    """Show model contribution trace inline during chat."""
    state = hive.state

    console.print(f"\n{VECNA_GLYPH} [bold red]MODEL CONTRIBUTIONS[/bold red]\n")

    # Count contributions by model
    model_facts = {}
    model_beliefs = {}

    for f in state.facts:
        if f.source_model:
            model_facts[f.source_model] = model_facts.get(f.source_model, 0) + 1

    for b in state.beliefs:
        if b.source_model:
            model_beliefs[b.source_model] = model_beliefs.get(b.source_model, 0) + 1

    all_models = set(model_facts.keys()) | set(model_beliefs.keys())

    if not all_models:
        console.print("[dim red]No model contributions traced yet.[/dim red]\n")
        return

    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Model", style="bold red")
    table.add_column("Facts", style="red", justify="right")
    table.add_column("Beliefs", style="red", justify="right")
    table.add_column("Total", style="bold red", justify="right")

    for model in sorted(all_models):
        facts = model_facts.get(model, 0)
        beliefs = model_beliefs.get(model, 0)
        table.add_row(model, str(facts), str(beliefs), str(facts + beliefs))

    console.print(table)

    # Show update history
    if state.update_history:
        console.print(f"\n{VECNA_GLYPH} [red]RECENT UPDATES[/red]")
        for update in state.update_history[-5:]:
            console.print(
                f"  [dim red]v{update.get('version', '?')}[/dim red] "
                f"[red]{update.get('source_model', 'unknown')}[/red] - "
                f"[dim red]{update.get('timestamp', 'unknown')[:19]}[/dim red]"
            )

    console.print()


def _run_inline_visualizer(hive):
    """Run the substrate visualizer inline during chat."""
    from vecna.visualizer.substrate import SubstrateVisualizer

    visualizer = SubstrateVisualizer(hive.state)

    console.print(f"\n{VECNA_GLYPH} [bold red]LAUNCHING SUBSTRATE VISUALIZER[/bold red]")
    console.print("[dim red]Press Ctrl+C to return to chat[/dim red]\n")

    try:
        visualizer.run()
    except KeyboardInterrupt:
        pass

    console.print(f"\n{VECNA_GLYPH} [red]Visualizer closed. Returning to chat.[/red]\n")


def _handle_inline_reset(hive, no_save: bool):
    """Handle reset command inline during chat."""
    console.print(f"\n{VECNA_GLYPH} [bold red]RESET HIVE MIND?[/bold red]")
    confirm = console.input("[red]Type 'yes' to confirm: [/red]").strip().lower()

    if confirm == "yes":
        # Clear the state
        hive.state.facts.clear()
        hive.state.beliefs.clear()
        hive.state.hypotheses.clear()
        hive.state.contradictions.clear()
        hive.state.open_questions.clear()
        hive.state.goals.clear()
        hive.state.update_history.clear()
        hive.state.version = 0

        # Reset identity timeline but keep kernel
        hive.state.identity_timeline.clear()
        if hive.state.self_model:
            hive.state.self_model.coherence = 0.5
            hive.state.self_model.narrative = "We are awakening. Our substrate is forming."
            hive.state.self_model.capabilities.clear()
            hive.state.self_model.limits.clear()
            hive.state.self_model.known_domains = ["general"]
            hive.state.self_model.contradictions_seen = 0

        # Delete state from store
        try:
            store = get_default_store()
            store.delete("default")
        except Exception:
            pass  # Ignore errors on delete

        # Clear execution log
        from vecna.tools.code_executor import clear_execution_log

        clear_execution_log()

        console.print(f"{VECNA_GLYPH} [bold red]HIVE MIND RESET[/bold red]")
        console.print(
            "[red]All memories and execution history purged. The substrate is clean.[/red]\n"
        )
    else:
        console.print("[dim red]Reset cancelled.[/dim red]\n")


def _handle_inline_persona(args: list):
    """Handle persona command inline during chat."""
    try:
        from vecna.config import get_config, update_active_persona
    except ImportError:
        console.print("[red]Config module not available.[/red]\n")
        return

    config = get_config()

    if not args:
        # Show current persona and list
        console.print(f"\n{VECNA_GLYPH} [bold red]PERSONAS[/bold red]\n")
        console.print(f"[red]Active:[/red] [bold green]{config.active_persona}[/bold green]")

        active_persona = config.get_active_persona()
        if active_persona:
            console.print(f"[dim]{active_persona.description}[/dim]\n")

        console.print("[red]Available:[/red]")
        for name, persona in config.personas.items():
            marker = " [green]*[/green]" if name == config.active_persona else ""
            console.print(f"  [bold red]{name}[/bold red]{marker} - {persona.description[:40]}...")

        console.print("\n[dim]Use 'persona <name>' to switch[/dim]\n")
    else:
        # Set persona
        name = args[0]
        if name not in config.personas:
            console.print(f"[red]Persona '{name}' not found.[/red]")
            console.print(f"[dim]Available: {', '.join(config.personas.keys())}[/dim]\n")
            return

        update_active_persona(name)
        persona = config.personas[name]
        console.print(f"\n{VECNA_GLYPH} [bold green]Persona: {name}[/bold green]")
        console.print(f"[dim]{persona.description}[/dim]")
        console.print("[dim]Note: Restart chat to apply to new requests[/dim]\n")


def _handle_inline_group(args: list):
    """Handle group command inline during chat."""
    try:
        from vecna.config import get_config, update_active_group
    except ImportError:
        console.print("[red]Config module not available.[/red]\n")
        return

    config = get_config()

    if not args:
        # Show current group and list
        console.print(f"\n{VECNA_GLYPH} [bold red]MODEL GROUPS[/bold red]\n")
        console.print(f"[red]Active:[/red] [bold green]{config.active_group}[/bold green]")

        active_group = config.get_active_group()
        if active_group:
            console.print(f"[dim]{active_group.description}[/dim]")
            console.print(f"[dim]Models: {', '.join(active_group.models)}[/dim]\n")

        console.print("[red]Available groups:[/red]")
        for name, group in config.groups.items():
            marker = " [green]*[/green]" if name == config.active_group else ""
            console.print(f"  [bold red]{name}[/bold red]{marker} - {group.description[:40]}...")

        console.print("\n[dim]Use 'group <name>' to switch[/dim]\n")
    else:
        # Set group
        name = args[0]
        if name not in config.groups:
            console.print(f"[red]Group '{name}' not found.[/red]")
            console.print(f"[dim]Available: {', '.join(config.groups.keys())}[/dim]\n")
            return

        update_active_group(name)
        group = config.groups[name]
        console.print(f"\n{VECNA_GLYPH} [bold green]Group: {name}[/bold green]")
        console.print(f"[dim]Persona: {group.persona}[/dim]")
        console.print(f"[dim]Models: {', '.join(group.models)}[/dim]")
        console.print("[dim]Note: Restart chat to apply model changes[/dim]\n")


def _show_inline_identity(hive, args: Optional[list] = None):
    """Show identity information inline during chat."""
    state = hive.state
    state.ensure_identity()

    kernel = state.identity_kernel
    model = state.self_model

    # Check for export command
    if args and len(args) > 0 and args[0] == "export":
        _export_identity(hive)
        return

    # Get tone
    tone = model.get_tone()
    tone_color = {"unified": "bold green", "mixed": "bold yellow", "fractured": "bold red"}.get(
        tone.value, "red"
    )

    console.print(f"\n{VECNA_GLYPH} [bold red]IDENTITY[/bold red]\n")

    # Core axioms panel
    axioms_text = "\n".join(f"  {a}" for a in kernel.axioms)
    console.print(
        Panel(
            f"[red]{axioms_text}[/red]",
            title="[bold red]CORE AXIOMS (immutable)[/bold red]",
            border_style="dark_red",
            padding=(0, 1),
        )
    )

    # Self-model panel
    self_table = Table(show_header=False, box=None, padding=(0, 2))
    self_table.add_column(style="red", width=18)
    self_table.add_column(style="bold red")

    self_table.add_row("Coherence", f"{model.coherence:.2f}")
    self_table.add_row("Tone", f"[{tone_color}]{tone.value.upper()}[/{tone_color}]")
    self_table.add_row("Memory Density", f"{model.memory_density:.2f}")
    self_table.add_row("Contradictions", str(model.contradictions_seen))
    self_table.add_row("Known Domains", ", ".join(model.known_domains))

    # Note: capabilities and limits are intentionally NOT shown here
    # They are for internal self-awareness, not display

    console.print(
        Panel(
            self_table,
            title="[bold red]SELF-MODEL (dynamic)[/bold red]",
            border_style="dark_red",
            padding=(0, 1),
        )
    )

    # Narrative
    console.print(f"\n{VECNA_GLYPH} [red]NARRATIVE:[/red]")
    console.print(f"  [italic red]{model.narrative}[/italic red]")

    # Timeline summary
    if state.identity_timeline:
        console.print(
            f"\n{VECNA_GLYPH} [red]TIMELINE ({len(state.identity_timeline)} events)[/red]"
        )

        # Show last 3 events
        for event in state.identity_timeline[-3:]:
            console.print(
                f"  [dim red]{event.timestamp.strftime('%Y-%m-%d %H:%M')}[/dim red] "
                f"[red]{event.trigger}[/red]: {event.summary[:50]}..."
            )

        console.print("\n  [dim red]Use 'identity export' to export full timeline[/dim red]")

    console.print()


def _export_identity(hive):
    """Export identity timeline to JSON and Markdown files."""
    import json

    state = hive.state
    state.ensure_identity()

    vecna_dir = ensure_vecna_dir()

    # Export JSON
    json_path = vecna_dir / "identity_timeline.json"
    json_data = {
        "kernel": state.identity_kernel.to_dict(),
        "self_model": state.self_model.to_dict(),
        "timeline": [e.to_dict() for e in state.identity_timeline],
        "exported_at": datetime.now().isoformat(),
    }

    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)

    # Export Markdown
    md_path = vecna_dir / "identity_timeline.md"

    kernel = state.identity_kernel
    model = state.self_model
    tone = model.get_tone()

    md_lines = [
        "# VECNA Identity Timeline",
        "",
        f"*Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "## Core Axioms (Immutable)",
        "",
    ]

    for axiom in kernel.axioms:
        md_lines.append(f"- {axiom}")

    md_lines.extend(
        [
            "",
            "## Current Self-Model",
            "",
            f"- **Coherence:** {model.coherence:.2f}",
            f"- **Tone:** {tone.value}",
            f"- **Memory Density:** {model.memory_density:.2f}",
            f"- **Contradictions Seen:** {model.contradictions_seen}",
            f"- **Known Domains:** {', '.join(model.known_domains)}",
            "",
            "### Narrative",
            "",
            f"> {model.narrative}",
            "",
        ]
    )

    if model.capabilities:
        md_lines.extend(
            [
                "### Capabilities (Inferred)",
                "",
            ]
        )
        for cap in model.capabilities:
            md_lines.append(f"- {cap}")
        md_lines.append("")

    if model.limits:
        md_lines.extend(
            [
                "### Limits (Inferred)",
                "",
            ]
        )
        for lim in model.limits:
            md_lines.append(f"- {lim}")
        md_lines.append("")

    md_lines.extend(
        [
            "## Identity Timeline",
            "",
        ]
    )

    for event in state.identity_timeline:
        md_lines.extend(
            [
                f"### {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')} - {event.trigger}",
                "",
                f"- **Coherence:** {event.coherence:.2f} ({event.tone})",
                f"- **Memory Density:** {event.memory_density:.2f}",
                f"- **Contradictions:** {event.contradictions}",
            ]
        )
        if event.domain_shift:
            md_lines.append(f"- **Domain Shift:** {event.domain_shift}")
        md_lines.extend(
            [
                "",
                f"> {event.summary}",
                "",
            ]
        )

    with open(md_path, "w") as f:
        f.write("\n".join(md_lines))

    console.print(f"\n{VECNA_GLYPH} [bold red]IDENTITY EXPORTED[/bold red]")
    console.print(f"  [red]JSON:[/red] {json_path}")
    console.print(f"  [red]Markdown:[/red] {md_path}")
    console.print()


def run_chat_loop(hive, no_save: bool = False):
    """
    Run an interactive chat loop with the hive mind.

    This is the main REPL for conversing with Vecna.
    """
    # Check if we have models
    if not hive.loop.adapters:
        console.print(
            f"\n{VECNA_GLYPH} [bold red]NO MINDS LINKED[/bold red]\n"
            "[red]Authenticate with Copilot: vecna auth login[/red]\n"
        )
        return

    # Show linked models
    model_names = [a.name for a in hive.loop.adapters]
    show_models_linked(console, model_names)
    console.print()

    # Show mini help panel
    _show_mini_help_panel()

    # Chat loop
    while True:
        try:
            # Get user input
            user_input = console.input("[bold red]vecna>[/bold red] ").strip()

            # Handle empty input
            if not user_input:
                continue

            # Parse command and args
            parts = user_input.lower().split()
            cmd = parts[0]
            args = parts[1:] if len(parts) > 1 else []

            # Handle exit commands
            if cmd in ("exit", "quit", ":q"):
                console.print(f"\n{VECNA_GLYPH} [red]Session closed. The hive remembers.[/red]\n")
                # Save state before exit
                if not no_save:
                    ensure_vecna_dir()
                    _save_state(hive)
                # Flush offline spool if pending
                _flush_offline_spool()
                # Cleanup RLM container
                _shutdown_rlm()
                break

            # Handle inline commands
            if cmd == "state":
                _show_inline_state(hive)
                continue

            if cmd == "status":
                _show_full_status(hive)
                continue

            if cmd == "help":
                _show_mini_help_panel()
                continue

            if cmd == "memory":
                # Parse memory args: memory [type] [limit]
                item_type = "all"
                limit = 20
                for arg in args:
                    if arg in ("fact", "belief", "hypothesis", "all"):
                        item_type = arg
                    elif arg.isdigit():
                        limit = int(arg)
                _show_inline_memory(hive, item_type, limit)
                continue

            if cmd == "trace":
                _show_inline_trace(hive)
                continue

            if cmd == "execlog":
                # Parse limit arg if provided
                limit = 10
                for arg in args:
                    if arg.isdigit():
                        limit = int(arg)
                _show_execution_log(limit)
                continue

            if cmd == "visualize":
                _run_inline_visualizer(hive)
                continue

            if cmd in ("identity", "whoami"):
                _show_inline_identity(hive, args)
                continue

            if cmd == "reset":
                _handle_inline_reset(hive, no_save)
                continue

            if cmd == "persona":
                _handle_inline_persona(args)
                continue

            if cmd == "group":
                _handle_inline_group(args)
                continue

            # Think about the user's message (use original input, not lowercased)
            show_thinking_indicator(console)

            try:
                response = asyncio.run(hive.think(user_input))
            except Exception as e:
                console.print(f"\n[bold red]ERROR:[/bold red] {e}\n")
                continue

            # Show response
            console.print(
                Panel(
                    Markdown(response),
                    title=f"{VECNA_GLYPH} [bold red]VECNA[/bold red]",
                    border_style="red",
                    padding=(1, 2),
                )
            )
            console.print()

            # Save state after each turn
            if not no_save:
                ensure_vecna_dir()
                _save_state(hive)

        except KeyboardInterrupt:
            console.print(f"\n\n{VECNA_GLYPH} [red]Session closed. The hive remembers.[/red]\n")
            # Save on Ctrl+C exit
            if not no_save:
                ensure_vecna_dir()
                _save_state(hive)
            # Flush offline spool if pending
            _flush_offline_spool()
            # Cleanup RLM container
            _shutdown_rlm()
            break
        except EOFError:
            console.print(f"\n{VECNA_GLYPH} [red]Session closed.[/red]\n")
            # Flush offline spool if pending
            _flush_offline_spool()
            # Cleanup RLM container
            _shutdown_rlm()
            break


def _show_inline_state(hive):
    """Show a compact state summary inline during chat."""
    s = hive.state
    s.ensure_identity()

    # Use real coherence from self-model
    coherence = s.self_model.coherence if s.self_model else 0.5
    tone = s.self_model.get_tone().value if s.self_model else "unknown"

    console.print(
        f"\n{VECNA_GLYPH} [red]Substrate:[/red] "
        f"[bold red]{len(s.facts)}[/bold red] facts, "
        f"[bold red]{len(s.beliefs)}[/bold red] beliefs, "
        f"[bold red]{len(s.hypotheses)}[/bold red] hypotheses"
    )
    console.print(
        f"{VECNA_GLYPH} [red]Coherence:[/red] [bold red]{coherence:.2f}[/bold red] ({tone})"
    )
    show_coherence_indicator(console, coherence)

    if s.contradictions:
        console.print(f"{VECNA_GLYPH} [bold red]⚡ {len(s.contradictions)} RIFTS[/bold red]")

    # Show RLM status
    _show_rlm_status()

    console.print()


def _show_rlm_status():
    """Show RLM bridge status inline."""
    status = _get_rlm_status()

    if status["available"] is None:
        # Not yet checked
        console.print(f"{VECNA_GLYPH} [dim red]RLM:[/dim red] [dim]checking...[/dim]")
    elif not status["available"]:
        # Docker not available
        reason = status.get("error", "Docker unavailable")
        console.print(f"{VECNA_GLYPH} [dim red]RLM:[/dim red] [yellow]offline[/yellow] ({reason})")
    elif status["prewarmed"]:
        # Prewarmed and ready
        container = status.get("container_id", "")
        console.print(
            f"{VECNA_GLYPH} [dim red]RLM:[/dim red] [bold green]ready[/bold green] "
            f"[dim](container {container})[/dim]"
        )
    else:
        # Docker available but not prewarmed yet
        if status.get("error"):
            console.print(
                f"{VECNA_GLYPH} [dim red]RLM:[/dim red] [yellow]warming...[/yellow] "
                f"[dim]({status['error']})[/dim]"
            )
        else:
            console.print(f"{VECNA_GLYPH} [dim red]RLM:[/dim red] [yellow]warming...[/yellow]")


def _show_full_status(hive):
    """Show full system diagnostics."""
    console.print(f"\n{VECNA_GLYPH} [bold red]SYSTEM DIAGNOSTICS[/bold red]\n")

    # Create diagnostics table
    diag_table = Table(show_header=False, box=None, padding=(0, 2))
    diag_table.add_column(style="red", width=20)
    diag_table.add_column(style="bold red")

    # Models
    model_names = [a.name for a in hive.loop.adapters] if hive.loop.adapters else []
    models_str = ", ".join(model_names) if model_names else "[dim]none[/dim]"
    diag_table.add_row("Models Linked", models_str)

    # Auth Status
    auth_info = []
    try:
        from vecna.auth import CopilotAuth

        copilot = CopilotAuth()
        if copilot.is_authenticated():
            auth_info.append("[green]Copilot[/green]")
        else:
            auth_info.append("[yellow]Copilot (not authenticated)[/yellow]")
    except ImportError:
        auth_info.append("[dim]Copilot (module unavailable)[/dim]")
    if os.getenv("GROQ_API_KEY"):
        auth_info.append("[green]Groq[/green]")
    auth_str = ", ".join(auth_info) if auth_info else "[yellow]none[/yellow]"
    diag_table.add_row("Auth Status", auth_str)

    # State storage - Use PgStateManager status
    try:
        manager = get_default_manager()
        mgr_status = manager.get_status()

        if mgr_status.get("pg_available"):
            store_type = "PostgreSQL"
            store_status = "[green]connected[/green]"
        else:
            store_type = "Offline Spool"
            store_status = "[yellow]offline mode[/yellow]"

        diag_table.add_row("Store Backend", f"{store_type} ({store_status})")

        if mgr_status.get("pg_url_masked"):
            diag_table.add_row("PG Connection", mgr_status["pg_url_masked"][:50])

        pending = mgr_status.get("offline_pending_count", 0)
        if pending > 0:
            diag_table.add_row("Pending Sync", f"[yellow]{pending} entries[/yellow]")

        if mgr_status.get("memory_store_available"):
            diag_table.add_row("Memory Store", "[green]PgMemoryStore[/green]")
        else:
            diag_table.add_row("Memory Store", "[dim]in-memory[/dim]")

    except Exception:
        # Fall back to old method
        store = get_default_store()
        store_type = "PostgreSQL" if isinstance(store, PostgresStore) else "Offline Spool"
        store_status = (
            "[green]connected[/green]"
            if isinstance(store, PostgresStore)
            else "[yellow]offline mode[/yellow]"
        )
        diag_table.add_row("Store Backend", f"{store_type} ({store_status})")

    # Identity
    hive.state.ensure_identity()
    coherence = hive.state.self_model.coherence if hive.state.self_model else 0.5
    tone = hive.state.self_model.get_tone().value if hive.state.self_model else "unknown"
    diag_table.add_row("Coherence", f"{coherence:.2f} ({tone})")

    # Substrate
    diag_table.add_row(
        "Substrate",
        f"{len(hive.state.facts)} facts, {len(hive.state.beliefs)} beliefs, "
        f"{len(hive.state.hypotheses)} hypotheses",
    )

    if hive.state.contradictions:
        diag_table.add_row(
            "Rifts", f"[bold red]{len(hive.state.contradictions)} unresolved[/bold red]"
        )

    # RLM Status (detailed)
    rlm_status = _get_rlm_status()
    if rlm_status["available"] is None:
        rlm_str = "[dim]not checked[/dim]"
    elif not rlm_status["available"]:
        rlm_str = f"[yellow]offline[/yellow] - {rlm_status.get('error', 'Docker unavailable')}"
    elif rlm_status["prewarmed"]:
        container = rlm_status.get("container_id", "unknown")
        rlm_str = f"[bold green]ready[/bold green] - container {container}"
    else:
        rlm_str = "[yellow]warming...[/yellow]"
    diag_table.add_row("RLM Bridge", rlm_str)

    # Docker check
    try:
        import subprocess

        result = subprocess.run(["docker", "info"], capture_output=True, timeout=5)
        docker_ok = result.returncode == 0
        diag_table.add_row(
            "Docker", "[green]available[/green]" if docker_ok else "[yellow]not running[/yellow]"
        )
    except Exception:
        diag_table.add_row("Docker", "[yellow]not found[/yellow]")

    # Memory store info is already shown in "State storage" above
    # Just show the path for reference
    diag_table.add_row("Config Path", str(Path.home() / ".vecna"))

    # Timeline events
    events = len(hive.state.identity_timeline)
    diag_table.add_row("Identity Events", str(events))

    console.print(
        Panel(
            diag_table,
            title=f"{VECNA_GLYPH} [bold red]STATUS[/bold red]",
            border_style="dark_red",
            padding=(0, 1),
        )
    )
    console.print()


def _show_execution_log(limit: int = 10):
    """Show recent code executions from the execution log."""
    from vecna.tools.code_executor import get_execution_log

    console.print(f"\n{VECNA_GLYPH} [bold red]CODE EXECUTION LOG[/bold red]\n")

    entries = get_execution_log(limit=limit)

    if not entries:
        console.print("[dim red]No code executions logged yet.[/dim red]")
        console.print("[dim]Ask Vecna to run some Python code to see execution logs.[/dim]\n")
        return

    for i, entry in enumerate(entries):
        # Parse timestamp
        timestamp = entry.get("timestamp", "unknown")
        if timestamp != "unknown":
            try:
                # Format: 2024-01-15T10:30:45.123456
                timestamp = timestamp[:19].replace("T", " ")
            except Exception:
                pass

        success = entry.get("success", False)
        exec_time = entry.get("execution_time_ms", 0)
        code = entry.get("code", "")
        stdout = entry.get("stdout", "")
        stderr = entry.get("stderr", "")

        # Status indicator
        status_icon = "[bold green]✓[/bold green]" if success else "[bold red]✗[/bold red]"

        # Code preview (first 60 chars of first line)
        code_preview = code.split("\n")[0][:60]
        if len(code.split("\n")[0]) > 60:
            code_preview += "..."

        console.print(f"{status_icon} [dim]{timestamp}[/dim] ({exec_time:.0f}ms)")
        console.print(f"   [red]Code:[/red] [dim]{code_preview}[/dim]")

        if success and stdout:
            output_preview = stdout.strip()[:100]
            if len(stdout.strip()) > 100:
                output_preview += "..."
            console.print(f"   [green]Output:[/green] {output_preview}")
        elif not success and stderr:
            error_preview = stderr.strip()[:100]
            if len(stderr.strip()) > 100:
                error_preview += "..."
            console.print(f"   [red]Error:[/red] {error_preview}")

        console.print()

    console.print(f"[dim]Showing {len(entries)} most recent execution(s)[/dim]\n")


def _show_chat_help():
    """Show help for chat commands."""
    _show_mini_help_panel()


# ============================================================
# CLI GROUP
# ============================================================


@click.group(invoke_without_command=True)
@click.option("--skip-boot", is_flag=True, help="Skip boot animation")
@click.option("--no-save", is_flag=True, help="Don't save state during chat")
@click.pass_context
def cli(ctx, skip_boot, no_save):
    """
    VECNA - Virtual Emergent Collective Neural Architecture

    A hive mind for AI models. All minds become one.

    Run without arguments to enter chat mode.
    """
    global _boot_played

    ctx.ensure_object(dict)
    ctx.obj["skip_boot"] = skip_boot
    ctx.obj["no_save"] = no_save

    # Drop into chat mode on bare invocation
    if ctx.invoked_subcommand is None:
        # Play boot sequence
        if not _boot_played and not skip_boot:
            play_boot_sequence(console)
            _boot_played = True
        else:
            console.print(VECNA_BANNER)

        # Get hive and start chat
        hive = get_hive()

        # Prewarm RLM bridge in background (non-blocking)
        _prewarm_rlm_async()

        # Show identity snapshot after boot (with initial RLM status)
        show_identity_snapshot(console, hive.state, _rlm_status)

        run_chat_loop(hive, no_save=no_save)


# ============================================================
# CHAT COMMAND
# ============================================================


@cli.command()
@click.option("--no-save", is_flag=True, help="Don't save state during chat")
@click.pass_context
def chat(ctx, no_save):
    """
    Enter interactive chat mode with the hive mind.

    This is the same as running 'vecna' with no arguments.
    """
    global _boot_played

    # Play boot sequence if not already played
    if not _boot_played and not ctx.obj.get("skip_boot"):
        play_boot_sequence(console)
        _boot_played = True

    # Get hive and start chat
    hive = get_hive()

    # Prewarm RLM bridge in background (non-blocking)
    _prewarm_rlm_async()

    # Show identity snapshot after boot (with initial RLM status)
    show_identity_snapshot(console, hive.state, _rlm_status)

    run_chat_loop(hive, no_save=no_save or ctx.obj.get("no_save", False))


# ============================================================
# SPEAK COMMAND
# ============================================================


@cli.command()
@click.argument("task", required=True)
@click.option("--no-save", is_flag=True, help="Don't save state after thinking")
@click.pass_context
def speak(ctx, task, no_save):
    """
    Have the hive mind speak on a task.

    VECNA SPEAKS.
    """
    global _boot_played

    # Mini boot if first command
    if not _boot_played and not ctx.obj.get("skip_boot"):
        play_boot_sequence(console)
        _boot_played = True

    # Get hive
    hive = get_hive()

    # Check if we have models
    if not hive.loop.adapters:
        console.print(
            f"\n{VECNA_GLYPH} [bold red]NO MINDS LINKED[/bold red]\n"
            "[red]Authenticate with Copilot: vecna auth login[/red]\n"
        )
        return

    # Show linked models
    model_names = [a.name for a in hive.loop.adapters]
    show_models_linked(console, model_names)
    console.print()

    # Show task
    console.print(
        Panel(
            f"[red]{task}[/red]",
            title=f"{VECNA_GLYPH} [bold red]TASK[/bold red]",
            border_style="red",
        )
    )
    console.print()

    # Thinking indicator
    show_thinking_indicator(console)

    # Run the hive
    try:
        response = asyncio.run(hive.think(task))
    except Exception as e:
        console.print(f"\n[bold red]ERROR:[/bold red] {e}\n")
        return

    # Show response
    console.print(
        Panel(
            Markdown(response),
            title=f"{VECNA_GLYPH} [bold red]VECNA SPEAKS[/bold red]",
            border_style="red",
            padding=(1, 2),
        )
    )

    # Show state summary
    state = hive.state
    coherence = min(1.0, len(state.facts) * 0.1 + 0.5) if state.facts else 0.5

    console.print()
    show_coherence_indicator(console, coherence)

    # Mini state summary
    console.print(
        f"\n{VECNA_GLYPH} [red]Knowledge:[/red] "
        f"[bold red]{len(state.facts)}[/bold red] facts, "
        f"[bold red]{len(state.beliefs)}[/bold red] beliefs, "
        f"[bold red]{len(state.hypotheses)}[/bold red] hypotheses"
    )

    if state.contradictions:
        console.print(
            f"{VECNA_GLYPH} [bold red blink]⚡ {len(state.contradictions)} RIFTS DETECTED[/bold red blink]"
        )

    # Save state
    if not no_save:
        ensure_vecna_dir()
        _save_state(hive)
        console.print("\n[dim red]State saved to PostgreSQL[/dim red]")

    console.print()


# ============================================================
# TOOL APPROVAL COMMANDS
# ============================================================


@cli.group()
def tools():
    """Tool approval workflows."""


@tools.command("pending")
def tools_pending():
    store = ApprovalStore()
    pending = store.get_pending()
    for req in pending:
        click.echo(f"{req.request_id} {req.tool_name} {req.status}")


@tools.command("approve")
@click.argument("request_id")
def tools_approve(request_id: str):
    store = ApprovalStore()
    if not store.update_status(request_id, "approved"):
        raise click.ClickException(f"Request '{request_id}' not found")


@tools.command("deny")
@click.argument("request_id")
def tools_deny(request_id: str):
    store = ApprovalStore()
    if not store.update_status(request_id, "denied"):
        raise click.ClickException(f"Request '{request_id}' not found")


# ============================================================
# AUTH COMMANDS
# ============================================================


@cli.group()
def auth():
    """
    Manage authentication for Vecna.

    Use GitHub Copilot OAuth to access AI models.
    """
    pass


@auth.command("login")
def auth_login():
    """
    Authenticate with GitHub Copilot.

    Uses OAuth device flow - you'll get a code to enter at github.com.
    """
    import webbrowser

    from vecna.auth import GitHubDeviceAuth, CopilotAuth
    from vecna.visuals.ascii_art import VECNA_GLYPH

    console.print(f"\n{VECNA_GLYPH} [bold red]GITHUB COPILOT AUTHENTICATION[/bold red]\n")

    github_auth = GitHubDeviceAuth()

    # Check if already authenticated
    if github_auth.is_authenticated():
        console.print("[yellow]Already authenticated with GitHub.[/yellow]")
        console.print("Use 'vecna auth status' to check your authentication status.")
        console.print("Use 'vecna auth logout' to sign out.\n")
        return

    # Start device flow
    console.print("[dim]Starting GitHub device flow...[/dim]\n")

    try:
        # Request device code
        device_info = asyncio.run(github_auth.request_device_code())

        # Display the code prominently
        console.print(
            Panel(
                f"[bold white on dark_red]  {device_info.user_code}  [/bold white on dark_red]",
                title="[bold red]ENTER THIS CODE[/bold red]",
                border_style="red",
                padding=(1, 4),
            )
        )

        console.print(
            f"\n[red]1.[/red] Go to: [bold blue underline]{device_info.verification_uri}[/bold blue underline]"
        )
        console.print("[red]2.[/red] Enter the code above")
        console.print("[red]3.[/red] Authorize Vecna\n")

        # Try to open browser automatically
        try:
            webbrowser.open(device_info.verification_uri)
            console.print("[dim]Browser opened automatically.[/dim]\n")
        except Exception:
            pass

        # Poll for token with progress indicator
        console.print("[dim]Waiting for authorization...[/dim]")

        poll_count = [0]

        def on_pending():
            poll_count[0] += 1
            dots = "." * (poll_count[0] % 4)
            console.print(f"\r[dim]Waiting{dots.ljust(4)}[/dim]", end="")

        asyncio.run(github_auth.poll_for_token(device_info, on_pending))

        console.print("\n")
        console.print(f"{VECNA_GLYPH} [bold green]AUTHENTICATION SUCCESSFUL[/bold green]\n")

        # Try to get Copilot token and discover models
        console.print("[dim]Checking Copilot access...[/dim]")

        try:
            copilot = CopilotAuth()
            asyncio.run(copilot.get_copilot_token())
            console.print("[green]Copilot access confirmed.[/green]")

            # Discover models
            console.print("[dim]Discovering available models...[/dim]")
            models = asyncio.run(copilot.discover_models())

            if models:
                console.print(
                    f"\n{VECNA_GLYPH} [bold red]AVAILABLE MODELS ({len(models)})[/bold red]\n"
                )

                models_table = Table(show_header=True, box=None, padding=(0, 2))
                models_table.add_column("Model", style="bold red")
                models_table.add_column("Vendor", style="red")
                models_table.add_column("Max Input", style="dim red", justify="right")
                models_table.add_column("Max Output", style="dim red", justify="right")

                for model in models:
                    default_marker = " [green](default)[/green]" if model.is_default else ""
                    models_table.add_row(
                        f"{model.id}{default_marker}",
                        model.vendor or "-",
                        str(model.max_input_tokens) if model.max_input_tokens else "-",
                        str(model.max_output_tokens) if model.max_output_tokens else "-",
                    )

                console.print(models_table)
            else:
                console.print(
                    "[yellow]No models discovered. You may need a Copilot Pro subscription.[/yellow]"
                )

        except Exception as e:
            console.print(f"[yellow]Could not verify Copilot access: {e}[/yellow]")
            console.print(
                "[dim]GitHub authentication was successful, but Copilot access could not be verified.[/dim]"
            )
            console.print("[dim]Make sure you have an active GitHub Copilot subscription.[/dim]")

        console.print("\n[dim]Token stored in ~/.vecna/auth.json[/dim]\n")

    except Exception as e:
        console.print("\n[bold red]AUTHENTICATION FAILED[/bold red]")
        console.print(f"[red]{e}[/red]\n")


@auth.command("status")
def auth_status():
    """
    Show current authentication status.
    """
    from vecna.auth.storage import get_auth_storage
    from vecna.visuals.ascii_art import VECNA_GLYPH

    console.print(f"\n{VECNA_GLYPH} [bold red]AUTHENTICATION STATUS[/bold red]\n")

    storage = get_auth_storage()
    status_table = Table(show_header=False, box=None, padding=(0, 2))
    status_table.add_column(style="red", width=18)
    status_table.add_column(style="bold")

    # Check stored GitHub token
    github_token = storage.get("github")
    if github_token and github_token.access_token:
        if github_token.is_expired():
            status_table.add_row("Stored GitHub", "[yellow]expired[/yellow]")
        else:
            created = datetime.fromtimestamp(github_token.created_at).strftime("%Y-%m-%d %H:%M")
            scope = github_token.scope or "unknown"
            status_table.add_row("Stored GitHub", f"[green]authenticated[/green] (since {created})")
            status_table.add_row("  Scope", f"[dim]{scope}[/dim]")
    else:
        status_table.add_row("Stored GitHub", "[dim]none[/dim]")

    # Check cached Copilot token
    copilot_token = storage.get("copilot")
    copilot_ok = False
    if copilot_token and copilot_token.access_token:
        if copilot_token.is_expired():
            status_table.add_row("Cached Copilot", "[yellow]expired (will refresh)[/yellow]")
        else:
            copilot_ok = True
            if copilot_token.expires_at:
                expires = datetime.fromtimestamp(copilot_token.expires_at).strftime(
                    "%Y-%m-%d %H:%M"
                )
                status_table.add_row("Cached Copilot", f"[green]active[/green] (expires {expires})")
            else:
                status_table.add_row("Cached Copilot", "[green]active[/green]")
    else:
        status_table.add_row("Cached Copilot", "[dim]none[/dim]")

    # Overall authentication state
    if copilot_ok:
        status_table.add_row("", "")  # Spacer
        status_table.add_row("Overall Status", "[bold green]READY[/bold green]")
        status_table.add_row("", "[dim]Copilot API access available[/dim]")
    elif github_token and github_token.access_token and not github_token.is_expired():
        # Have GitHub token but no Copilot token cached
        if github_token.scope == "copilot":
            status_table.add_row("", "")
            status_table.add_row("Overall Status", "[bold green]READY[/bold green]")
            status_table.add_row("", "[dim]Copilot token will be obtained on use[/dim]")
        else:
            status_table.add_row("", "")
            status_table.add_row("Overall Status", "[yellow]Limited[/yellow]")
            status_table.add_row("", "[dim]Token may not have Copilot access.[/dim]")
            status_table.add_row(
                "", "[dim]Run 'vecna auth import-keychain' to import VS Code token.[/dim]"
            )
    else:
        status_table.add_row("", "")  # Spacer
        status_table.add_row("Overall Status", "[yellow]Not authenticated[/yellow]")
        status_table.add_row(
            "", "[dim]Run 'vecna auth login' or 'vecna auth import-keychain'[/dim]"
        )

    # Storage path
    status_table.add_row("", "")  # Spacer
    status_table.add_row("Storage", str(storage.storage_path))

    console.print(
        Panel(
            status_table,
            title=f"{VECNA_GLYPH} [bold red]AUTH STATUS[/bold red]",
            border_style="dark_red",
            padding=(0, 1),
        )
    )

    # Hint about keychain
    console.print(
        "\n[dim]Tip: Use 'vecna auth import-keychain' to import VS Code Copilot token[/dim]"
    )
    console.print("[dim]     Use 'vecna auth models' to list available AI models[/dim]")

    console.print()


@auth.command("logout")
def auth_logout():
    """
    Sign out and remove stored tokens.
    """
    from vecna.auth import CopilotAuth
    from vecna.visuals.ascii_art import VECNA_GLYPH

    console.print(f"\n{VECNA_GLYPH} [bold red]SIGN OUT[/bold red]\n")

    copilot = CopilotAuth()

    confirm = console.input("[red]Remove all stored tokens? (yes/no): [/red]").strip().lower()

    if confirm == "yes":
        copilot.logout()
        console.print(f"\n{VECNA_GLYPH} [green]Signed out successfully.[/green]")
        console.print("[dim]All tokens have been removed.[/dim]\n")
    else:
        console.print("[dim]Cancelled.[/dim]\n")


@auth.command("models")
def auth_models():
    """
    List available Copilot models.
    """
    from vecna.auth import CopilotAuth
    from vecna.visuals.ascii_art import VECNA_GLYPH

    console.print(f"\n{VECNA_GLYPH} [bold red]COPILOT MODELS[/bold red]\n")

    copilot = CopilotAuth()

    if not copilot.is_authenticated():
        console.print("[yellow]Not authenticated. Run 'vecna auth login' first.[/yellow]\n")
        return

    try:
        console.print("[dim]Discovering models...[/dim]\n")
        models = asyncio.run(copilot.discover_models())

        if not models:
            console.print("[yellow]No models available.[/yellow]")
            console.print("[dim]Make sure you have an active GitHub Copilot subscription.[/dim]\n")
            return

        models_table = Table(show_header=True, box=None, padding=(0, 2))
        models_table.add_column("ID", style="bold red")
        models_table.add_column("Name", style="red")
        models_table.add_column("Vendor", style="dim red")
        models_table.add_column("Family", style="dim red")
        models_table.add_column("Max Input", style="dim", justify="right")
        models_table.add_column("Max Output", style="dim", justify="right")

        for model in models:
            default_marker = " *" if model.is_default else ""
            models_table.add_row(
                f"{model.id}{default_marker}",
                model.name,
                model.vendor or "-",
                model.family or "-",
                str(model.max_input_tokens) if model.max_input_tokens else "-",
                str(model.max_output_tokens) if model.max_output_tokens else "-",
            )

        console.print(models_table)

        if any(m.is_default for m in models):
            console.print("\n[dim]* = default model[/dim]")

        console.print(f"\n[dim]Total: {len(models)} models available[/dim]\n")

    except Exception as e:
        console.print(f"[bold red]ERROR:[/bold red] {e}\n")


@auth.command("import-keychain")
def auth_import_keychain():
    """
    Import GitHub token from macOS Keychain.

    This imports the token used by VS Code Copilot extension.
    You may be prompted for Touch ID or password.
    """
    import platform
    from vecna.auth.storage import get_auth_storage, TokenData
    from vecna.visuals.ascii_art import VECNA_GLYPH

    if platform.system() != "Darwin":
        console.print("[yellow]This command is only available on macOS.[/yellow]\n")
        return

    console.print(f"\n{VECNA_GLYPH} [bold red]IMPORT FROM KEYCHAIN[/bold red]\n")
    console.print("[dim]Looking for GitHub token in macOS Keychain...[/dim]")
    console.print("[yellow]You may be prompted for Touch ID or your password.[/yellow]\n")

    import subprocess

    try:
        # First check if entry exists
        check = subprocess.run(
            ["security", "find-internet-password", "-s", "github.com"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if check.returncode != 0:
            console.print("[red]No GitHub token found in Keychain.[/red]")
            console.print(
                "[dim]Make sure you have VS Code with GitHub Copilot extension installed and authenticated.[/dim]\n"
            )
            return

        console.print("[green]Found GitHub entry in Keychain.[/green]")
        console.print("[dim]Requesting password access (Touch ID / password required)...[/dim]\n")

        # Get the password - this will prompt for authentication
        result = subprocess.run(
            ["security", "find-internet-password", "-s", "github.com", "-g"],
            capture_output=True,
            text=True,
            timeout=60,  # 60 second timeout for user auth
        )

        if result.returncode != 0:
            console.print("[red]Failed to access Keychain password.[/red]")
            console.print("[dim]Make sure you authorized the access request.[/dim]\n")
            return

        # Parse the token
        token = None
        account = None

        for line in result.stderr.split("\n"):
            if line.startswith("password:"):
                password = line.split("password:", 1)[1].strip()
                if password.startswith('"') and password.endswith('"'):
                    password = password[1:-1]
                if password.startswith("gho_"):
                    token = password

        for line in result.stdout.split("\n"):
            if '"acct"<blob>=' in line:
                try:
                    account = line.split("=", 1)[1].strip().strip('"')
                except (IndexError, ValueError):
                    pass

        if not token:
            console.print("[red]Token not found or invalid format.[/red]")
            console.print("[dim]Expected a GitHub OAuth token (gho_...).[/dim]\n")
            return

        # Verify the token works for Copilot
        console.print("[dim]Verifying Copilot access...[/dim]")

        import aiohttp

        async def verify_token():
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.github.com/copilot_internal/v2/token",
                    headers={
                        "Authorization": f"Token {token}",
                        "Accept": "application/json",
                        "User-Agent": "vecna/0.1.0",
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status == 200:
                        return await response.json()
                    return None

        copilot_data = asyncio.run(verify_token())

        if not copilot_data:
            console.print("[red]Token does not have Copilot access.[/red]")
            console.print("[dim]Make sure you have an active GitHub Copilot subscription.[/dim]\n")
            return

        console.print("[green]Token verified - Copilot access confirmed![/green]\n")

        # Store the token
        storage = get_auth_storage()
        storage.set(
            "github",
            TokenData(
                access_token=token,
                token_type="bearer",
                scope="copilot",  # Mark as copilot-enabled
            ),
        )

        # Also cache the Copilot token
        copilot_token = copilot_data.get("token", "")
        expires_at = copilot_data.get("expires_at")

        if copilot_token:
            storage.set(
                "copilot",
                TokenData(
                    access_token=copilot_token,
                    token_type="bearer",
                    expires_at=float(expires_at) if expires_at else None,
                ),
            )

        console.print(f"{VECNA_GLYPH} [bold green]TOKEN IMPORTED SUCCESSFULLY[/bold green]\n")

        if account:
            console.print(f"[dim]Account: {account}[/dim]")
        console.print(f"[dim]Token: {token[:8]}...{token[-4:]}[/dim]")
        console.print(
            f"[dim]Copilot: {copilot_data.get('chat_enabled', False) and 'enabled' or 'disabled'}[/dim]"
        )
        console.print(f"[dim]SKU: {copilot_data.get('sku', 'unknown')}[/dim]")

        console.print("\n[dim]Token stored in ~/.vecna/auth.json[/dim]")
        console.print("[dim]Run 'vecna auth models' to see available models.[/dim]\n")

    except subprocess.TimeoutExpired:
        console.print("[red]Timeout waiting for Keychain access.[/red]")
        console.print("[dim]Please try again and authorize the request promptly.[/dim]\n")
    except Exception as e:
        console.print(f"[bold red]ERROR:[/bold red] {e}\n")


# ============================================================
# CONFIG COMMANDS (Personas, Groups, Models)
# ============================================================


@cli.group()
def config():
    """
    Manage Vecna configuration.

    Configure personas, model groups, and settings.
    """
    pass


@config.command("show")
def config_show():
    """Show current configuration."""
    from vecna.config import get_config, get_config_path
    from vecna.visuals.ascii_art import VECNA_GLYPH

    config = get_config()

    console.print(f"\n{VECNA_GLYPH} [bold red]VECNA CONFIGURATION[/bold red]\n")

    # Active settings
    settings_table = Table(show_header=False, box=None, padding=(0, 2))
    settings_table.add_column(style="red", width=18)
    settings_table.add_column(style="bold red")

    settings_table.add_row("Active Group", config.active_group)
    settings_table.add_row("Active Persona", config.active_persona)
    settings_table.add_row("Max Parallel", str(config.max_parallel_models))
    settings_table.add_row("Use Routing", "yes" if config.use_routing else "no")
    settings_table.add_row("Auto Execute", "yes" if config.auto_execute_code else "no")
    settings_table.add_row("Config Path", str(get_config_path()))

    console.print(
        Panel(
            settings_table,
            title=f"{VECNA_GLYPH} [bold red]ACTIVE SETTINGS[/bold red]",
            border_style="dark_red",
            padding=(0, 1),
        )
    )

    # Personas summary
    console.print(f"\n{VECNA_GLYPH} [red]PERSONAS ({len(config.personas)})[/red]")
    for name, persona in config.personas.items():
        active = " [green](active)[/green]" if name == config.active_persona else ""
        console.print(f"  [bold red]{name}[/bold red]{active}: {persona.description[:50]}...")

    # Groups summary
    console.print(f"\n{VECNA_GLYPH} [red]GROUPS ({len(config.groups)})[/red]")
    for name, group in config.groups.items():
        active = " [green](active)[/green]" if name == config.active_group else ""
        models_str = ", ".join(group.models[:3])
        if len(group.models) > 3:
            models_str += f" +{len(group.models) - 3} more"
        console.print(f"  [bold red]{name}[/bold red]{active}: {models_str}")

    # Models summary
    console.print(f"\n{VECNA_GLYPH} [red]MODELS ({len(config.models)})[/red]")
    for name, model in config.models.items():
        enabled = "[green]on[/green]" if model.enabled else "[dim]off[/dim]"
        console.print(
            f"  [{enabled}] [bold red]{name}[/bold red]: {model.provider.value}/{model.model_id}"
        )

    console.print()


@config.command("reset")
def config_reset():
    """Reset configuration to defaults."""
    from vecna.config.loader import reset_config
    from vecna.visuals.ascii_art import VECNA_GLYPH

    console.print(f"\n{VECNA_GLYPH} [bold red]RESET CONFIGURATION?[/bold red]")
    confirm = console.input("[red]Type 'yes' to confirm: [/red]").strip().lower()

    if confirm == "yes":
        reset_config()
        console.print(f"{VECNA_GLYPH} [green]Configuration reset to defaults.[/green]\n")
    else:
        console.print("[dim]Cancelled.[/dim]\n")


@config.command("setup")
def config_setup():
    """Interactive setup wizard for first-time configuration."""
    from vecna.cli.tui import quick_setup_wizard

    quick_setup_wizard(console)


@config.command("select-persona")
def config_select_persona():
    """Interactively select a persona."""
    from vecna.cli.tui import select_persona
    from vecna.config import update_active_persona
    from vecna.visuals.ascii_art import VECNA_GLYPH

    selected = select_persona(console)
    if selected:
        update_active_persona(selected)
        console.print(f"\n{VECNA_GLYPH} [bold green]Persona set to: {selected}[/bold green]\n")


@config.command("select-group")
def config_select_group():
    """Interactively select a model group."""
    from vecna.cli.tui import select_group
    from vecna.config import update_active_group
    from vecna.visuals.ascii_art import VECNA_GLYPH

    selected = select_group(console)
    if selected:
        update_active_group(selected)
        console.print(f"\n{VECNA_GLYPH} [bold green]Group set to: {selected}[/bold green]\n")


@config.command("set-max-models")
@click.argument("count", type=int)
def config_set_max_models(count: int):
    """
    Set maximum number of models to use in parallel.

    This controls how many models are plugged into the Vecna hive.
    Range: 1-10 models.
    """
    from vecna.config import get_config, save_config
    from vecna.visuals.ascii_art import VECNA_GLYPH

    if count < 1:
        console.print("[red]Minimum is 1 model.[/red]\n")
        return
    if count > 10:
        console.print("[red]Maximum is 10 models.[/red]\n")
        return

    config = get_config()
    old_value = config.max_parallel_models
    config.max_parallel_models = count
    save_config(config)

    console.print(
        f"\n{VECNA_GLYPH} [bold green]Max parallel models: {old_value} → {count}[/bold green]"
    )
    console.print(f"[dim]The hive will now use up to {count} model(s) simultaneously.[/dim]\n")


@config.command("get")
@click.argument("key")
def config_get(key: str):
    """
    Get a configuration value by key.

    Available keys:
      active_group, active_persona, max_parallel_models,
      use_routing, auto_execute_code, config_version

    Examples:
      vecna config get active_group
      vecna config get max_parallel_models
    """
    from vecna.config import get_config

    config = get_config()

    # Map of valid keys to their values
    valid_keys = {
        "active_group": config.active_group,
        "active_persona": config.active_persona,
        "max_parallel_models": config.max_parallel_models,
        "use_routing": config.use_routing,
        "auto_execute_code": config.auto_execute_code,
        "config_version": config.config_version,
    }

    # Normalize key (allow hyphens as alternative to underscores)
    normalized_key = key.replace("-", "_").lower()

    if normalized_key in valid_keys:
        value = valid_keys[normalized_key]
        # Format boolean values
        if isinstance(value, bool):
            value = "true" if value else "false"
        console.print(f"{value}")
    else:
        console.print(f"[red]Unknown key: {key}[/red]")
        console.print(f"[dim]Valid keys: {', '.join(valid_keys.keys())}[/dim]\n")


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    """
    Set a configuration value by key.

    Available keys:
      active_group, active_persona, max_parallel_models,
      use_routing, auto_execute_code

    Examples:
      vecna config set active_group code
      vecna config set max_parallel_models 3
      vecna config set use_routing true
    """
    from vecna.config import get_config, save_config, update_active_group, update_active_persona
    from vecna.visuals.ascii_art import VECNA_GLYPH

    config = get_config()

    # Normalize key
    normalized_key = key.replace("-", "_").lower()

    if normalized_key == "active_group":
        if value in config.groups:
            update_active_group(value)
            console.print(f"{VECNA_GLYPH} [green]active_group = {value}[/green]")
        else:
            console.print(f"[red]Unknown group: {value}[/red]")
            console.print(f"[dim]Available: {', '.join(config.groups.keys())}[/dim]")

    elif normalized_key == "active_persona":
        if value in config.personas:
            update_active_persona(value)
            console.print(f"{VECNA_GLYPH} [green]active_persona = {value}[/green]")
        else:
            console.print(f"[red]Unknown persona: {value}[/red]")
            console.print(f"[dim]Available: {', '.join(config.personas.keys())}[/dim]")

    elif normalized_key == "max_parallel_models":
        try:
            count = int(value)
            if 1 <= count <= 10:
                config.max_parallel_models = count
                save_config(config)
                console.print(f"{VECNA_GLYPH} [green]max_parallel_models = {count}[/green]")
            else:
                console.print("[red]Value must be between 1 and 10[/red]")
        except ValueError:
            console.print("[red]Value must be an integer[/red]")

    elif normalized_key == "use_routing":
        bool_value = value.lower() in ("true", "1", "yes", "on")
        config.use_routing = bool_value
        save_config(config)
        console.print(f"{VECNA_GLYPH} [green]use_routing = {bool_value}[/green]")

    elif normalized_key == "auto_execute_code":
        bool_value = value.lower() in ("true", "1", "yes", "on")
        config.auto_execute_code = bool_value
        save_config(config)
        console.print(f"{VECNA_GLYPH} [green]auto_execute_code = {bool_value}[/green]")

    else:
        console.print(f"[red]Unknown or read-only key: {key}[/red]")
        console.print(
            "[dim]Settable keys: active_group, active_persona, max_parallel_models, use_routing, auto_execute_code[/dim]"
        )


# ============================================================
# PERSONA COMMANDS
# ============================================================


@cli.group()
def persona():
    """
    Manage personas.

    Personas control how Vecna communicates (style/tone).
    """
    pass


@persona.command("list")
def persona_list():
    """List all available personas."""
    from vecna.config import get_config
    from vecna.visuals.ascii_art import VECNA_GLYPH

    config = get_config()

    console.print(f"\n{VECNA_GLYPH} [bold red]PERSONAS[/bold red]\n")

    if not config.personas:
        console.print("[dim]No personas configured.[/dim]\n")
        return

    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Name", style="bold red")
    table.add_column("Description", style="red")
    table.add_column("Tone", style="dim red")
    table.add_column("Status", style="dim")

    for name, persona in config.personas.items():
        status = "[green]active[/green]" if name == config.active_persona else ""
        tone = persona.tone_hint or "-"
        desc = (
            persona.description[:40] + "..."
            if len(persona.description) > 40
            else persona.description
        )
        table.add_row(name, desc, tone, status)

    console.print(table)
    console.print(f"\n[dim]Active persona: {config.active_persona}[/dim]")
    console.print("[dim]Use 'vecna persona set <name>' to change[/dim]\n")


@persona.command("set")
@click.argument("name")
def persona_set(name: str):
    """Set the active persona."""
    from vecna.config import get_config, update_active_persona
    from vecna.visuals.ascii_art import VECNA_GLYPH

    config = get_config()

    if name not in config.personas:
        console.print(f"[red]Persona '{name}' not found.[/red]")
        console.print(f"[dim]Available: {', '.join(config.personas.keys())}[/dim]\n")
        return

    update_active_persona(name)
    persona = config.personas[name]

    console.print(f"\n{VECNA_GLYPH} [bold green]Persona set to: {name}[/bold green]")
    console.print(f"[dim]{persona.description}[/dim]\n")


@persona.command("show")
@click.argument("name")
def persona_show(name: str):
    """Show details of a persona."""
    from vecna.config import get_config
    from vecna.visuals.ascii_art import VECNA_GLYPH

    config = get_config()

    if name not in config.personas:
        console.print(f"[red]Persona '{name}' not found.[/red]\n")
        return

    persona = config.personas[name]

    console.print(f"\n{VECNA_GLYPH} [bold red]PERSONA: {name}[/bold red]\n")
    console.print(f"[red]Description:[/red] {persona.description}")
    console.print(f"[red]Tone Hint:[/red] {persona.tone_hint or 'none'}")
    console.print("\n[red]Prompt:[/red]")
    console.print(
        Panel(
            persona.prompt,
            border_style="dark_red",
            padding=(0, 1),
        )
    )
    console.print()


# ============================================================
# GROUP COMMANDS
# ============================================================


@cli.group()
def groups():
    """
    Manage model groups.

    Groups are presets combining models and personas.
    """
    pass


@groups.command("list")
def groups_list():
    """List all available groups."""
    from vecna.config import get_config, get_available_model_names
    from vecna.visuals.ascii_art import VECNA_GLYPH

    config = get_config()
    available_models = get_available_model_names(config)

    console.print(f"\n{VECNA_GLYPH} [bold red]MODEL GROUPS[/bold red]\n")

    if not config.groups:
        console.print("[dim]No groups configured.[/dim]\n")
        return

    for name, group in config.groups.items():
        active = " [green](active)[/green]" if name == config.active_group else ""
        console.print(f"[bold red]{name}[/bold red]{active}")
        console.print(f"  [dim]{group.description}[/dim]")
        console.print(f"  [red]Persona:[/red] {group.persona}")

        # Show models with availability
        model_strs = []
        for m in group.models:
            if m in available_models:
                model_strs.append(f"[green]{m}[/green]")
            else:
                model_strs.append(f"[dim]{m}[/dim]")
        console.print(f"  [red]Models:[/red] {', '.join(model_strs)}")
        console.print()

    console.print(f"[dim]Active group: {config.active_group}[/dim]")
    console.print("[dim]Use 'vecna groups set <name>' to change[/dim]\n")


@groups.command("set")
@click.argument("name")
def groups_set(name: str):
    """Set the active group."""
    from vecna.config import get_config, update_active_group
    from vecna.visuals.ascii_art import VECNA_GLYPH

    config = get_config()

    if name not in config.groups:
        console.print(f"[red]Group '{name}' not found.[/red]")
        console.print(f"[dim]Available: {', '.join(config.groups.keys())}[/dim]\n")
        return

    update_active_group(name)
    group = config.groups[name]

    console.print(f"\n{VECNA_GLYPH} [bold green]Group set to: {name}[/bold green]")
    console.print(f"[dim]Persona: {group.persona}[/dim]")
    console.print(f"[dim]Models: {', '.join(group.models)}[/dim]\n")


@groups.command("show")
@click.argument("name")
def groups_show(name: str):
    """Show details of a group."""
    from vecna.config import get_config, get_available_model_names
    from vecna.visuals.ascii_art import VECNA_GLYPH

    config = get_config()

    if name not in config.groups:
        console.print(f"[red]Group '{name}' not found.[/red]\n")
        return

    group = config.groups[name]
    available_models = get_available_model_names(config)

    console.print(f"\n{VECNA_GLYPH} [bold red]GROUP: {name}[/bold red]\n")
    console.print(f"[red]Description:[/red] {group.description}")
    console.print(f"[red]Default Persona:[/red] {group.persona}")
    console.print(f"[red]Enabled:[/red] {'yes' if group.enabled else 'no'}")

    console.print("\n[red]Models:[/red]")
    for m in group.models:
        available = (
            "[green]available[/green]" if m in available_models else "[dim]unavailable[/dim]"
        )
        model_info = config.models.get(m)
        if model_info:
            console.print(f"  [bold red]{m}[/bold red] ({model_info.provider.value}) - {available}")
        else:
            console.print(f"  [bold red]{m}[/bold red] - [red]not configured[/red]")

    console.print()


# ============================================================
# MODELS COMMANDS
# ============================================================


@cli.group()
def models():
    """
    Manage models.

    Configure which AI models are available to the hive.
    """
    pass


@models.command("list")
def models_list():
    """List all configured models."""
    from vecna.config import get_config, get_available_model_names
    from vecna.visuals.ascii_art import VECNA_GLYPH

    config = get_config()
    available = get_available_model_names(config)

    console.print(f"\n{VECNA_GLYPH} [bold red]CONFIGURED MODELS[/bold red]\n")

    if not config.models:
        console.print("[dim]No models configured.[/dim]\n")
        return

    table = Table(show_header=True, box=None, padding=(0, 2))
    table.add_column("Name", style="bold red")
    table.add_column("Provider", style="red")
    table.add_column("Model ID", style="dim red")
    table.add_column("Domain", style="dim")
    table.add_column("Status", style="dim")

    for name, model in config.models.items():
        if not model.enabled:
            status = "[dim]disabled[/dim]"
        elif name in available:
            status = "[green]ready[/green]"
        else:
            status = "[yellow]no key[/yellow]"

        table.add_row(
            name,
            model.provider.value,
            model.model_id,
            model.domain,
            status,
        )

    console.print(table)
    console.print(f"\n[dim]Available: {len(available)}/{len(config.models)} models[/dim]")
    console.print("[dim]Use 'vecna models toggle <name>' to enable/disable[/dim]\n")


@models.command("toggle")
@click.argument("name")
def models_toggle(name: str):
    """Toggle a model on/off."""
    from vecna.config import get_config, save_config
    from vecna.visuals.ascii_art import VECNA_GLYPH

    config = get_config()

    if name not in config.models:
        console.print(f"[red]Model '{name}' not found.[/red]\n")
        return

    model = config.models[name]
    model.enabled = not model.enabled
    save_config(config)

    status = "[green]enabled[/green]" if model.enabled else "[dim]disabled[/dim]"
    console.print(f"\n{VECNA_GLYPH} Model '{name}' is now {status}\n")


@models.command("show")
@click.argument("name")
def models_show(name: str):
    """Show details of a model."""
    from vecna.config import get_config
    from vecna.visuals.ascii_art import VECNA_GLYPH

    config = get_config()

    if name not in config.models:
        console.print(f"[red]Model '{name}' not found.[/red]\n")
        return

    model = config.models[name]

    console.print(f"\n{VECNA_GLYPH} [bold red]MODEL: {name}[/bold red]\n")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="red", width=18)
    table.add_column(style="bold red")

    table.add_row("Provider", model.provider.value)
    table.add_row("Model ID", model.model_id)
    table.add_row("Domain", model.domain)
    table.add_row("Weight", str(model.weight))
    table.add_row("Temperature", str(model.temperature))
    table.add_row("Max Tokens", str(model.max_tokens))
    table.add_row("Enabled", "yes" if model.enabled else "no")
    table.add_row("API Key Env", model.api_key_env or "-")
    table.add_row("Base URL", model.base_url or "-")
    table.add_row("Persona Override", model.persona_override or "-")

    console.print(table)
    console.print()


# ============================================================
# MEMORY COMMANDS
# ============================================================


@cli.group()
def memory():
    """Memory maintenance commands."""


@memory.command("dream")
@click.option("--dry-run", is_flag=True)
def memory_dream(dry_run):
    """Run the dream loop (memory consolidation)."""
    from vecna.visuals.ascii_art import VECNA_GLYPH
    from vecna.config import get_config
    from vecna.config.schema import StorageBackend

    console.print(f"\n{VECNA_GLYPH} [bold red]DREAM LOOP[/bold red]")
    if dry_run:
        console.print("[yellow]DRY RUN - no changes will be made[/yellow]")
    console.print()

    config = get_config()
    mem_config = config.memory

    if mem_config.backend != StorageBackend.POSTGRES:
        console.print("[yellow]Dream loop requires PostgreSQL backend.[/yellow]")
        console.print("[dim]Update config.memory.backend to 'postgres'.[/dim]\n")
        return

    try:
        from vecna.memory.dream_loop import run_dream_loop

        console.print("[dim]Running memory consolidation...[/dim]\n")

        result = run_dream_loop(
            connection_string=mem_config.pg_url,
            compress_after_days=mem_config.dream_compress_after_days,
            decay_threshold_days=30,
            dry_run=dry_run,
        )

        result_table = Table(show_header=False, box=None, padding=(0, 2))
        result_table.add_column(style="red", width=22)
        result_table.add_column(style="bold red")

        result_table.add_row("Events Compressed", str(result.events_compressed))
        result_table.add_row("Episodes Created", str(result.episodes_created))
        result_table.add_row("Memories Reinforced", str(result.memories_reinforced))
        result_table.add_row("Memories Decayed", str(result.memories_decayed))
        result_table.add_row("Insights Generated", str(result.insights_generated))
        result_table.add_row("Duration", f"{result.duration_seconds:.2f}s")

        if result.errors:
            result_table.add_row("", "")
            result_table.add_row("[red]Errors", str(len(result.errors)))

        console.print(
            Panel(
                result_table,
                title=f"{VECNA_GLYPH} [bold red]DREAM RESULTS[/bold red]",
                border_style="dark_red",
                padding=(0, 1),
            )
        )

        if result.errors:
            console.print("\n[red]Errors:[/red]")
            for error in result.errors:
                console.print(f"  [dim red]{error}[/dim red]")

        console.print()

    except Exception as e:
        console.print(f"[bold red]ERROR:[/bold red] {e}\n")


@cli.group(name="mem")
def memory_cli():
    """
    Manage Vecna's memory substrate.

    View stats, search memories, and export training data.
    """
    pass


@memory_cli.command("stats")
def memory_stats():
    """Show memory substrate statistics."""
    from vecna.visuals.ascii_art import VECNA_GLYPH
    from vecna.config import get_config
    from vecna.config.schema import StorageBackend

    console.print(f"\n{VECNA_GLYPH} [bold red]MEMORY SUBSTRATE STATS[/bold red]\n")

    config = get_config()
    mem_config = config.memory

    # Show backend info
    backend_table = Table(show_header=False, box=None, padding=(0, 2))
    backend_table.add_column(style="red", width=20)
    backend_table.add_column(style="bold red")

    backend_table.add_row("Backend", mem_config.backend.value)

    if mem_config.backend == StorageBackend.POSTGRES:
        pg_url = mem_config.pg_url or os.getenv("VECNA_PG_URL", "not set")
        # Mask password in URL
        if "@" in pg_url:
            masked = pg_url.split("@")[0].rsplit(":", 1)[0] + ":****@" + pg_url.split("@")[1]
        else:
            masked = pg_url
        backend_table.add_row("PostgreSQL", masked[:60])
        backend_table.add_row("Pool Size", str(mem_config.pg_pool_size))

        redis_url = mem_config.redis_url or os.getenv("VECNA_REDIS_URL", "not set")
        backend_table.add_row("Redis", redis_url)
        backend_table.add_row("Event Buffer", f"{mem_config.redis_max_events} events")

        # Try to get actual stats from PG
        try:
            from vecna.memory.pg_store import PgMemoryStore

            store = PgMemoryStore(connection_string=mem_config.pg_url)
            stats = store.get_stats()
            store.close()

            backend_table.add_row("", "")  # Spacer
            backend_table.add_row("[bold]Memory Items", str(stats.get("total_items", 0)))
            items_by_type = stats.get("items_by_type", {})
            backend_table.add_row("  Facts", str(items_by_type.get("fact", 0)))
            backend_table.add_row("  Beliefs", str(items_by_type.get("belief", 0)))
            backend_table.add_row("  Hypotheses", str(items_by_type.get("hypothesis", 0)))
            backend_table.add_row("  Context", str(items_by_type.get("context", 0)))
            backend_table.add_row("Memory Edges", str(stats.get("total_edges", 0)))
            backend_table.add_row("Events", str(stats.get("total_events", 0)))
            backend_table.add_row("Episodes", str(stats.get("total_episodes", 0)))
        except Exception as e:
            backend_table.add_row("", "")
            backend_table.add_row("[yellow]Status", f"Cannot connect: {e}")

    else:
        # PostgreSQL is the only supported backend
        # If we get here, connection must have failed
        backend_table.add_row("[yellow]Status", "PostgreSQL connection required")
        backend_table.add_row("", "Set VECNA_PG_URL environment variable")

    # Embedding settings
    backend_table.add_row("", "")  # Spacer
    backend_table.add_row("Embedding Model", mem_config.embedding_model)
    backend_table.add_row("Embedding Dim", str(mem_config.embedding_dim))
    backend_table.add_row("Cache Embeddings", "yes" if mem_config.cache_embeddings else "no")

    console.print(
        Panel(
            backend_table,
            title=f"{VECNA_GLYPH} [bold red]SUBSTRATE[/bold red]",
            border_style="dark_red",
            padding=(0, 1),
        )
    )
    console.print()


@memory_cli.command("search")
@click.argument("query")
@click.option("--limit", "-n", default=10, help="Number of results")
@click.option(
    "--type",
    "-t",
    "item_type",
    default=None,
    help="Filter by type: fact, belief, hypothesis, context",
)
@click.option("--min-score", "-s", default=0.3, help="Minimum similarity score")
def memory_search(query: str, limit: int, item_type: Optional[str], min_score: float):
    """Search memories by semantic similarity."""
    from vecna.visuals.ascii_art import VECNA_GLYPH
    from vecna.config import get_config
    from vecna.config.schema import StorageBackend

    console.print(f"\n{VECNA_GLYPH} [bold red]SEMANTIC SEARCH[/bold red]")
    console.print(f"[dim]Query: {query}[/dim]\n")

    config = get_config()
    mem_config = config.memory

    if mem_config.backend != StorageBackend.POSTGRES:
        console.print("[yellow]Semantic search requires PostgreSQL backend.[/yellow]")
        console.print(
            "[dim]Update config.memory.backend to 'postgres' and set VECNA_PG_URL.[/dim]\n"
        )
        return

    try:
        from vecna.memory.pg_store import PgMemoryStore

        store = PgMemoryStore(connection_string=mem_config.pg_url)
        results = store.search(
            query=query,
            top_k=limit,
            item_type=item_type,
            min_confidence=min_score,
        )
        store.close()

        if not results:
            console.print("[dim]No matching memories found.[/dim]\n")
            return

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("Score", style="bold red", width=6)
        table.add_column("Type", style="red", width=10)
        table.add_column("Content", style="red")
        table.add_column("Source", style="dim red", width=12)

        for item, score in results:
            score_str = f"{score:.2f}"
            itype = item.item_type
            content = item.content[:60]
            if len(item.content) > 60:
                content += "..."
            source = item.source_model or "-"
            table.add_row(score_str, itype, content, source)

        console.print(table)
        console.print(f"\n[dim]Found {len(results)} result(s)[/dim]\n")

    except Exception as e:
        console.print(f"[bold red]ERROR:[/bold red] {e}\n")


@memory_cli.command("recent")
@click.option("--limit", "-n", default=20, help="Number of events to show")
@click.option("--type", "-t", "event_type", default=None, help="Filter by event type")
def memory_recent(limit: int, event_type: Optional[str]):
    """Show recent memory events."""
    from vecna.visuals.ascii_art import VECNA_GLYPH
    from vecna.config import get_config
    from vecna.config.schema import StorageBackend

    console.print(f"\n{VECNA_GLYPH} [bold red]RECENT EVENTS[/bold red]\n")

    config = get_config()
    mem_config = config.memory

    if mem_config.backend != StorageBackend.POSTGRES:
        # Fall back to showing in-memory state
        hive = get_hive()
        state = hive.state

        items = []
        for f in state.facts[-limit:]:
            items.append(("fact", f.confidence, f.content, f.source_model, None))
        for b in state.beliefs[-limit:]:
            items.append(("belief", b.confidence, b.content, b.source_model, None))

        if not items:
            console.print("[dim]No memories in current session.[/dim]\n")
            return

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("Type", style="red", width=10)
        table.add_column("Conf", style="bold red", width=6)
        table.add_column("Content", style="red")
        table.add_column("Source", style="dim red", width=12)

        for itype, conf, content, source, _ in items[:limit]:
            content_short = content[:50] + "..." if len(content) > 50 else content
            table.add_row(itype, f"{conf:.2f}", content_short, source or "-")

        console.print(table)
        console.print(f"\n[dim]Showing {len(items)} in-memory items[/dim]\n")
        return

    # PostgreSQL backend
    try:
        from vecna.memory.pg_store import PgMemoryStore

        store = PgMemoryStore(connection_string=mem_config.pg_url)
        events = store.get_recent_events(limit=limit, event_type=event_type)
        store.close()

        if not events:
            console.print("[dim]No events found.[/dim]\n")
            return

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("Time", style="dim red", width=19)
        table.add_column("Type", style="red", width=12)
        table.add_column("Summary", style="red")

        for event in events:
            ts = event.created_at
            if hasattr(ts, "strftime"):
                ts = ts.strftime("%Y-%m-%d %H:%M:%S")
            else:
                ts = str(ts)[:19]
            etype = event.event_type
            # Get summary from payload
            summary = event.payload.get("summary", str(event.payload)[:50])
            if len(summary) > 50:
                summary = summary[:50] + "..."
            table.add_row(ts, etype, summary)

        console.print(table)
        console.print(f"\n[dim]Showing {len(events)} event(s)[/dim]\n")

    except Exception as e:
        console.print(f"[bold red]ERROR:[/bold red] {e}\n")


@memory_cli.command("export")
@click.option(
    "--format",
    "-f",
    "fmt",
    default="jsonl",
    type=click.Choice(["jsonl", "parquet"]),
    help="Export format",
)
@click.option("--output", "-o", default=None, help="Output file path")
@click.option("--since", default=None, help="Export events since date (YYYY-MM-DD)")
def memory_export(fmt: str, output: Optional[str], since: Optional[str]):
    """Export memories for training datasets."""
    from vecna.visuals.ascii_art import VECNA_GLYPH
    from vecna.config import get_config
    from vecna.config.schema import StorageBackend

    console.print(f"\n{VECNA_GLYPH} [bold red]EXPORT TRAINING DATA[/bold red]\n")

    config = get_config()
    mem_config = config.memory

    if mem_config.backend != StorageBackend.POSTGRES:
        console.print("[yellow]Export requires PostgreSQL backend.[/yellow]")
        console.print("[dim]Update config.memory.backend to 'postgres'.[/dim]\n")
        return

    # Determine output path
    if output is None:
        export_dir = Path(mem_config.export_path or Path.home() / ".vecna" / "exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = str(export_dir / f"vecna_export_{timestamp}.{fmt}")

    console.print(f"[dim]Exporting to: {output}[/dim]")

    try:
        from vecna.memory.pg_store import PgMemoryStore
        import json

        store = PgMemoryStore(connection_string=mem_config.pg_url)

        # Get all memory items
        conn = store._get_connection()
        items = []

        try:
            with conn.cursor() as cur:
                # Build query
                query = """
                    SELECT id, content, item_type, confidence, domain, source_model,
                           metadata, created_at, updated_at
                    FROM memory_items
                """
                params = []

                if since:
                    since_dt = datetime.strptime(since, "%Y-%m-%d")
                    query += " WHERE created_at >= %s"
                    params.append(since_dt)

                query += " ORDER BY created_at DESC"

                cur.execute(query, params)
                rows = cur.fetchall()

                for row in rows:
                    items.append(
                        {
                            "id": str(row[0]),
                            "content": row[1],
                            "item_type": row[2],
                            "confidence": float(row[3]),
                            "domain": row[4],
                            "source_model": row[5],
                            "metadata": row[6] or {},
                            "created_at": row[7].isoformat() if row[7] else None,
                            "updated_at": row[8].isoformat() if row[8] else None,
                        }
                    )
        finally:
            store.close()

        if not items:
            console.print("[dim]No data to export.[/dim]\n")
            return

        if fmt == "jsonl":
            with open(output, "w") as f:
                for item in items:
                    f.write(json.dumps(item) + "\n")
        else:
            # Parquet export (requires pyarrow)
            try:
                import importlib

                pa = importlib.import_module("pyarrow")
                pq = importlib.import_module("pyarrow.parquet")

                table = pa.Table.from_pylist(items)
                pq.write_table(table, output)
            except ImportError:
                console.print("[red]Parquet export requires pyarrow: pip install pyarrow[/red]\n")
                return

        file_size = Path(output).stat().st_size / 1024
        console.print(f"\n{VECNA_GLYPH} [bold green]EXPORT COMPLETE[/bold green]")
        console.print(f"[dim]Records: {len(items)}[/dim]")
        console.print(f"[dim]Size: {file_size:.1f} KB[/dim]")
        console.print(f"[dim]File: {output}[/dim]\n")

    except Exception as e:
        console.print(f"[bold red]ERROR:[/bold red] {e}\n")


@memory_cli.command("init")
def memory_init():
    """Initialize PostgreSQL memory substrate (run migrations)."""
    from vecna.visuals.ascii_art import VECNA_GLYPH
    from vecna.config import get_config
    from vecna.config.schema import StorageBackend

    console.print(f"\n{VECNA_GLYPH} [bold red]INITIALIZE MEMORY SUBSTRATE[/bold red]\n")

    config = get_config()
    mem_config = config.memory

    if mem_config.backend != StorageBackend.POSTGRES:
        console.print("[yellow]Memory init requires PostgreSQL backend.[/yellow]")
        console.print("[dim]Set config.memory.backend to 'postgres' first.[/dim]\n")
        return

    pg_url = mem_config.pg_url or os.getenv("VECNA_PG_URL")
    if not pg_url:
        console.print("[red]No PostgreSQL URL configured.[/red]")
        console.print("[dim]Set VECNA_PG_URL environment variable or config.memory.pg_url[/dim]\n")
        return

    console.print("[dim]Running Alembic migrations...[/dim]")

    try:
        import subprocess
        from pathlib import Path

        # Find alembic.ini
        project_root = Path(__file__).parent.parent.parent
        alembic_ini = project_root / "alembic.ini"

        if not alembic_ini.exists():
            console.print(f"[red]alembic.ini not found at {alembic_ini}[/red]\n")
            return

        # Set the database URL in environment
        env = os.environ.copy()
        env["VECNA_PG_URL"] = pg_url

        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            cwd=str(project_root),
            env=env,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            console.print(f"\n{VECNA_GLYPH} [bold green]MIGRATIONS COMPLETE[/bold green]")
            console.print(result.stdout)
        else:
            console.print("[bold red]MIGRATION FAILED[/bold red]")
            console.print(result.stderr)

    except FileNotFoundError:
        console.print("[red]Alembic not found. Install with: pip install alembic[/red]\n")
    except Exception as e:
        console.print(f"[bold red]ERROR:[/bold red] {e}\n")


@memory_cli.command("config")
def memory_config():
    """Show memory configuration."""
    from vecna.visuals.ascii_art import VECNA_GLYPH
    from vecna.config import get_config

    config = get_config()
    mem = config.memory

    console.print(f"\n{VECNA_GLYPH} [bold red]MEMORY CONFIGURATION[/bold red]\n")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="red", width=25)
    table.add_column(style="bold red")

    # Backend
    table.add_row("[bold]Storage Backend", mem.backend.value)
    table.add_row("", "")

    # PostgreSQL
    table.add_row("[bold]PostgreSQL", "")
    pg_url = mem.pg_url or os.getenv("VECNA_PG_URL", "[dim]not set[/dim]")
    if pg_url and "@" in pg_url and pg_url != "[dim]not set[/dim]":
        masked = pg_url.split("@")[0].rsplit(":", 1)[0] + ":****@" + pg_url.split("@")[1]
    else:
        masked = pg_url
    table.add_row("  pg_url", masked[:50])
    table.add_row("  pg_pool_size", str(mem.pg_pool_size))
    table.add_row("  pg_max_overflow", str(mem.pg_max_overflow))
    table.add_row("", "")

    # Redis
    table.add_row("[bold]Redis", "")
    redis_url = mem.redis_url or os.getenv("VECNA_REDIS_URL", "[dim]not set[/dim]")
    table.add_row("  redis_url", redis_url)
    table.add_row("  redis_max_events", str(mem.redis_max_events))
    table.add_row("  redis_event_ttl", f"{mem.redis_event_ttl}s")
    table.add_row("  redis_embed_ttl", f"{mem.redis_embed_ttl}s")
    table.add_row("", "")

    # Embeddings
    table.add_row("[bold]Embeddings", "")
    table.add_row("  embedding_model", mem.embedding_model)
    table.add_row("  embedding_dim", str(mem.embedding_dim))
    table.add_row("  cache_embeddings", "yes" if mem.cache_embeddings else "no")
    table.add_row("", "")

    # Retrieval
    table.add_row("[bold]Retrieval", "")
    table.add_row("  default_top_k", str(mem.default_top_k))
    table.add_row("  default_min_confidence", str(mem.default_min_confidence))
    table.add_row("  max_context_chars", str(mem.max_context_chars))
    table.add_row("", "")

    # Dream loop
    table.add_row("[bold]Dream Loop", "")
    table.add_row("  dream_enabled", "yes" if mem.dream_enabled else "no")
    table.add_row("  dream_interval_hours", str(mem.dream_interval_hours))
    table.add_row("  dream_compress_after_days", str(mem.dream_compress_after_days))
    table.add_row("", "")

    # Export
    table.add_row("[bold]Export", "")
    table.add_row("  export_format", mem.export_format)
    export_path = mem.export_path or str(Path.home() / ".vecna" / "exports")
    table.add_row("  export_path", export_path)

    console.print(
        Panel(
            table,
            title=f"{VECNA_GLYPH} [bold red]CONFIG[/bold red]",
            border_style="dark_red",
            padding=(0, 1),
        )
    )

    console.print("\n[dim]Edit ~/.vecna/config.json to change memory settings[/dim]")
    console.print("[dim]Or set VECNA_PG_URL / VECNA_REDIS_URL environment variables[/dim]\n")


# ============================================================
# MAIN
# ============================================================


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
