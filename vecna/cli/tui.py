"""
Vecna TUI - Interactive Terminal UI for model and persona selection.

Uses rich library for interactive selection menus.
"""

from typing import List, Optional
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from vecna.visuals.ascii_art import VECNA_GLYPH


def select_from_list(
    console: Console,
    title: str,
    items: List[dict],
    current: Optional[str] = None,
    name_key: str = "name",
    desc_key: str = "description",
) -> Optional[str]:
    """
    Display a numbered list and let user select an item.

    Args:
        console: Rich console instance
        title: Title for the selection panel
        items: List of dicts with name and description
        current: Currently selected item name (highlighted)
        name_key: Key for item name in dict
        desc_key: Key for item description in dict

    Returns:
        Selected item name or None if cancelled
    """
    console.print(f"\n{VECNA_GLYPH} [bold red]{title}[/bold red]\n")

    if not items:
        console.print("[dim]No items available.[/dim]\n")
        return None

    # Build numbered list
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold red", width=4, justify="right")
    table.add_column(style="red")
    table.add_column(style="dim red")

    for i, item in enumerate(items, 1):
        name = item.get(name_key, "")
        desc = item.get(desc_key, "")[:50]
        marker = " [green]*[/green]" if name == current else ""
        table.add_row(f"[{i}]", f"{name}{marker}", desc)

    console.print(table)
    console.print("\n[dim]Enter number to select, or 'q' to cancel[/dim]")

    # Get selection
    try:
        choice = Prompt.ask("[red]Select[/red]", default="q")

        if choice.lower() == "q":
            return None

        idx = int(choice) - 1
        if 0 <= idx < len(items):
            return items[idx].get(name_key)
        else:
            console.print("[red]Invalid selection.[/red]\n")
            return None

    except (ValueError, KeyboardInterrupt):
        return None


def select_persona(console: Console) -> Optional[str]:
    """Interactive persona selection."""
    try:
        from vecna.config import get_config
    except ImportError:
        console.print("[red]Config module not available.[/red]\n")
        return None

    config = get_config()

    items = [
        {
            "name": name,
            "description": persona.description,
        }
        for name, persona in config.personas.items()
    ]

    return select_from_list(
        console,
        "SELECT PERSONA",
        items,
        current=config.active_persona,
    )


def select_group(console: Console) -> Optional[str]:
    """Interactive group selection."""
    try:
        from vecna.config import get_config
    except ImportError:
        console.print("[red]Config module not available.[/red]\n")
        return None

    config = get_config()

    items = [
        {
            "name": name,
            "description": f"{group.description} ({len(group.models)} models)",
        }
        for name, group in config.groups.items()
    ]

    return select_from_list(
        console,
        "SELECT GROUP",
        items,
        current=config.active_group,
    )


def select_models(console: Console) -> Optional[List[str]]:
    """Interactive multi-model selection."""
    try:
        from vecna.config import get_config, get_available_model_names
    except ImportError:
        console.print("[red]Config module not available.[/red]\n")
        return None

    config = get_config()
    available = get_available_model_names(config)

    console.print(f"\n{VECNA_GLYPH} [bold red]SELECT MODELS[/bold red]\n")

    if not config.models:
        console.print("[dim]No models configured.[/dim]\n")
        return None

    # Build numbered list with availability status
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold red", width=4, justify="right")
    table.add_column(style="red")
    table.add_column(style="dim")
    table.add_column(style="dim red")

    model_names = list(config.models.keys())
    for i, name in enumerate(model_names, 1):
        model = config.models[name]
        status = "[green]ready[/green]" if name in available else "[yellow]no key[/yellow]"
        if not model.enabled:
            status = "[dim]disabled[/dim]"
        provider = model.provider.value
        table.add_row(f"[{i}]", name, status, provider)

    console.print(table)
    console.print(
        "\n[dim]Enter numbers separated by commas (e.g., '1,3,4'), or 'q' to cancel[/dim]"
    )

    # Get selection
    try:
        choice = Prompt.ask("[red]Select[/red]", default="q")

        if choice.lower() == "q":
            return None

        indices = [int(x.strip()) - 1 for x in choice.split(",")]
        selected = []
        for idx in indices:
            if 0 <= idx < len(model_names):
                selected.append(model_names[idx])

        if selected:
            return selected
        else:
            console.print("[red]No valid selections.[/red]\n")
            return None

    except (ValueError, KeyboardInterrupt):
        return None


def quick_setup_wizard(console: Console) -> bool:
    """
    Interactive setup wizard for first-time users.

    Returns True if setup was completed, False if cancelled.
    """
    try:
        from vecna.config import (
            get_config,
            save_config,
            update_active_group,
            update_active_persona,
            get_available_model_names,
        )
    except ImportError:
        console.print("[red]Config module not available.[/red]\n")
        return False

    config = get_config()
    available = get_available_model_names(config)

    console.print(f"\n{VECNA_GLYPH} [bold red]VECNA SETUP WIZARD[/bold red]\n")

    # Step 1: Check available models
    console.print("[red]Step 1:[/red] Available Models\n")

    if not available:
        console.print("[yellow]No models are currently available.[/yellow]")
        console.print("[dim]Authenticate with GitHub Copilot:[/dim]")
        console.print("[dim]  vecna auth login[/dim]")
        console.print("[dim]Or set GROQ_API_KEY for Groq models.[/dim]\n")

        cont = Prompt.ask("[red]Continue anyway?[/red]", choices=["y", "n"], default="n")
        if cont != "y":
            return False
    else:
        console.print(f"[green]Found {len(available)} available model(s):[/green]")
        for name in available:
            model = config.models.get(name)
            if model:
                console.print(f"  [bold red]{name}[/bold red] ({model.provider.value})")
        console.print()

    # Step 2: Select a group
    console.print("[red]Step 2:[/red] Select a Model Group\n")

    group_name = select_group(console)
    if group_name:
        update_active_group(group_name)
        console.print(f"[green]Group set to: {group_name}[/green]\n")
    else:
        console.print("[dim]Keeping default group.[/dim]\n")

    # Step 3: Select a persona
    console.print("[red]Step 3:[/red] Select a Persona\n")

    persona_name = select_persona(console)
    if persona_name:
        update_active_persona(persona_name)
        console.print(f"[green]Persona set to: {persona_name}[/green]\n")
    else:
        console.print("[dim]Keeping default persona.[/dim]\n")

    # Step 4: Set max parallel models
    console.print("[red]Step 4:[/red] Max Parallel Models\n")
    console.print(
        f"[dim]Current: {config.max_parallel_models} | Controls how many models think simultaneously.[/dim]\n"
    )

    try:
        max_input = Prompt.ask(
            "[red]Max parallel models (1-10)[/red]", default=str(config.max_parallel_models)
        )
        max_count = int(max_input)
        if 1 <= max_count <= 10:
            config.max_parallel_models = max_count
            save_config(config)
            console.print(f"[green]Max models set to: {max_count}[/green]\n")
        else:
            console.print("[yellow]Invalid range. Keeping current value.[/yellow]\n")
    except (ValueError, KeyboardInterrupt):
        console.print("[dim]Keeping current value.[/dim]\n")

    # Summary
    console.print(f"\n{VECNA_GLYPH} [bold green]SETUP COMPLETE[/bold green]\n")

    config = get_config()  # Reload
    console.print(f"[red]Active Group:[/red] {config.active_group}")
    console.print(f"[red]Active Persona:[/red] {config.active_persona}")
    console.print(f"[red]Max Parallel:[/red] {config.max_parallel_models}")
    console.print(f"[red]Available Models:[/red] {len(available)}")

    console.print("\n[dim]Run 'vecna' to start chatting![/dim]\n")

    return True
