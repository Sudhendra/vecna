"""
Live subconscious substrate visualizer (Rich).

Renders VECNA as a growing organism:
- Central nucleus (✶) representing the hive core
- Radial growth rings with facts/beliefs/hypotheses as nodes
- Vine-like tendrils connecting nodes to the core
- Contradiction rifts as scar lines across the substrate
- Pulse animation driven by coherence

Stranger Things aesthetic: vines, rifts, organic growth.
Optimized for 80x24 terminal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional
import math

from rich.console import Console, Group
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live
from rich.box import MINIMAL, ROUNDED

from vecna.core.hive_state import HiveState
from vecna.visuals.theme import STYLES, VECNA_STYLES, VECNA_COLORS


# ============================================================
# GLYPHS - Stranger Things / Vecna organism
# ============================================================

GLYPHS = {
    "core": "✶",
    "core_pulse": "✴",
    "fact": "●",
    "belief": "◉",
    "hypothesis": "○",
    "rift": "╳",
    "tendril_h": "─",
    "tendril_v": "│",
    "tendril_dr": "╲",
    "tendril_dl": "╱",
    "tendril_node": "·",
    "pulse_ring": "•",
    "empty": " ",
}


@dataclass
class Node:
    id: str
    label: str
    node_type: str
    confidence: float
    source: str
    index: int  # insertion order for deterministic placement


class SubstrateVisualizer:
    """
    Renders a live organism representation of the hive state.

    The substrate grows outward from a central nucleus (✶),
    with nodes placed in radial rings based on recency.
    Tendrils (vines) connect nodes to the core.
    Contradictions manifest as rift scars.
    """

    # Grid dimensions optimized for 80x24 terminal
    GRID_WIDTH = 54
    GRID_HEIGHT = 12

    def __init__(self, state: HiveState, refresh_rate: float = 0.8):
        self.state = state
        self.refresh_rate = refresh_rate
        self.console = Console()
        self._tick = 0

    def run(self) -> None:
        import time

        with Live(self._render(), refresh_per_second=4, console=self.console) as live:
            while True:
                time.sleep(self.refresh_rate)
                self._tick += 1
                live.update(self._render())

    def _render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=3),
        )
        layout["body"].split_row(
            Layout(name="substrate", ratio=3),
            Layout(name="sidebar", ratio=2),
        )
        layout["sidebar"].split_column(
            Layout(name="updates", ratio=3),
            Layout(name="legend", size=6),
        )

        layout["header"].update(self._render_header())
        layout["substrate"].update(self._render_substrate())
        layout["updates"].update(self._render_updates())
        layout["legend"].update(self._render_legend())
        layout["footer"].update(self._render_footer())

        return layout

    def _render_header(self) -> Panel:
        coherence = self._coherence_score()
        node_count = self._node_count()

        # Pulse indicator based on tick
        pulse_char = "▮" if self._tick % 4 < 2 else "▯"

        text = Text()
        text.append("VECNA", style=VECNA_STYLES["banner"])
        text.append("  │  ", style=VECNA_STYLES["dim"])
        text.append("SUBSTRATE", style=VECNA_STYLES["header"])
        text.append(f"  │  Coherence: ", style=VECNA_STYLES["dim"])
        text.append(f"{coherence:.2f}", style=VECNA_STYLES["highlight"])
        text.append(f"  │  Nodes: ", style=VECNA_STYLES["dim"])
        text.append(f"{node_count}", style=VECNA_STYLES["text"])
        text.append(f"  │  ", style=VECNA_STYLES["dim"])
        text.append(
            pulse_char, style=VECNA_STYLES["warning"] if self._tick % 4 < 2 else VECNA_STYLES["dim"]
        )

        return Panel(text, style=VECNA_STYLES["border"], box=MINIMAL)

    def _render_substrate(self) -> Panel:
        grid = self._build_organism_grid()
        text = Text()

        for row in grid:
            line = "".join(row)
            # Apply styling per character type
            styled_line = Text()
            for char in line:
                style = self._glyph_style(char)
                styled_line.append(char, style=style)
            text.append_text(styled_line)
            text.append("\n")

        return Panel(
            text,
            title="[bold]THE UPSIDE DOWN[/bold]",
            border_style=VECNA_STYLES["border"],
            box=ROUNDED,
        )

    def _render_updates(self) -> Panel:
        table = Table.grid(padding=(0, 1))
        table.add_column(justify="left", width=28)

        table.add_row(Text("MEMORY STREAM", style=VECNA_STYLES["header"]))
        table.add_row(Text("", style=VECNA_STYLES["dim"]))

        # Show recent facts
        for fact in self.state.facts[-3:]:
            label = f"● {fact.content[:24]}"
            conf_style = (
                VECNA_STYLES["conf_high"] if fact.confidence >= 0.8 else VECNA_STYLES["conf_medium"]
            )
            table.add_row(Text(label, style=conf_style))

        # Show recent beliefs
        for belief in self.state.beliefs[-2:]:
            label = f"◉ {belief.content[:24]}"
            table.add_row(Text(label, style=VECNA_STYLES["belief"]))

        # Show recent hypotheses
        for hyp in self.state.hypotheses[-2:]:
            label = f"○ {hyp.content[:24]}"
            table.add_row(Text(label, style=VECNA_STYLES["hypothesis"]))

        return Panel(
            table,
            title="[dim]STREAM[/dim]",
            border_style=VECNA_STYLES["border"],
            box=ROUNDED,
        )

    def _render_legend(self) -> Panel:
        """Minimal legend panel explaining glyphs."""
        text = Text()
        text.append("✶", style=VECNA_STYLES["warning"])
        text.append(" core  ", style=VECNA_STYLES["dim"])
        text.append("●", style=VECNA_STYLES["fact"])
        text.append(" fact\n", style=VECNA_STYLES["dim"])
        text.append("◉", style=VECNA_STYLES["belief"])
        text.append(" belief ", style=VECNA_STYLES["dim"])
        text.append("○", style=VECNA_STYLES["hypothesis"])
        text.append(" hypo\n", style=VECNA_STYLES["dim"])
        text.append("╳", style=VECNA_STYLES["contradiction"])
        text.append(" rift  ", style=VECNA_STYLES["dim"])
        text.append("─", style=VECNA_STYLES["muted"])
        text.append(" vine", style=VECNA_STYLES["dim"])

        return Panel(
            text,
            title="[dim]LEGEND[/dim]",
            border_style=VECNA_STYLES["border"],
            box=MINIMAL,
        )

    def _render_footer(self) -> Panel:
        contradictions = len(self.state.contradictions)
        open_qs = len([q for q in self.state.open_questions if q.status == "open"])
        goals = len([g for g in self.state.goals if g.status == "active"])

        text = Text()
        if contradictions > 0:
            text.append(f"╳ RIFTS: {contradictions}  ", style=VECNA_STYLES["contradiction"])
        else:
            text.append("╳ RIFTS: 0  ", style=VECNA_STYLES["dim"])
        text.append(f"? OPEN: {open_qs}  ", style=VECNA_STYLES["question"])
        text.append(f"◆ GOALS: {goals}", style=VECNA_STYLES["goal"])

        return Panel(text, style=VECNA_STYLES["border"], box=MINIMAL)

    # ============================================================
    # ORGANISM GRID BUILDER
    # ============================================================

    def _build_organism_grid(self) -> List[List[str]]:
        """
        Build the substrate as a growing organism.

        - Core nucleus at center
        - Nodes placed in radial rings by recency
        - Tendrils connecting nodes to core
        - Rifts for contradictions
        """
        width = self.GRID_WIDTH
        height = self.GRID_HEIGHT
        grid = [[GLYPHS["empty"] for _ in range(width)] for _ in range(height)]

        cx, cy = width // 2, height // 2  # center

        # 1. Draw tendrils first (background layer)
        nodes = self._collect_nodes()
        node_positions = self._compute_node_positions(nodes, cx, cy, width, height)
        self._draw_tendrils(grid, cx, cy, node_positions)

        # 2. Draw rift scars if contradictions exist
        if self.state.contradictions:
            self._draw_rifts(grid, width, height)

        # 3. Place nodes
        for node, (x, y) in zip(nodes, node_positions):
            if 0 <= x < width and 0 <= y < height:
                grid[y][x] = self._node_glyph(node)

        # 4. Place core nucleus (on top)
        core_glyph = GLYPHS["core_pulse"] if self._tick % 6 < 3 else GLYPHS["core"]
        grid[cy][cx] = core_glyph

        # 5. Draw pulse ring around core based on coherence
        if self._coherence_score() > 0.5:
            self._draw_pulse_ring(grid, cx, cy, width, height)

        return grid

    def _compute_node_positions(
        self, nodes: List[Node], cx: int, cy: int, width: int, height: int
    ) -> List[Tuple[int, int]]:
        """
        Compute deterministic positions for nodes in radial rings.

        Older nodes are closer to the core; newer nodes are farther out.
        Angle is based on node index for stable placement.
        """
        positions = []
        total = len(nodes)
        if total == 0:
            return positions

        max_radius_x = (width // 2) - 2
        max_radius_y = (height // 2) - 1

        for i, node in enumerate(nodes):
            # Radius grows with index (newer = farther)
            # Use sqrt for tighter inner rings
            t = (i + 1) / (total + 1)
            radius_factor = math.sqrt(t)

            # Angle based on golden ratio for even spread
            golden_angle = 2.399963  # ~137.5 degrees in radians
            angle = i * golden_angle

            # Compute position with aspect ratio correction
            rx = int(cx + radius_factor * max_radius_x * math.cos(angle))
            ry = int(cy + radius_factor * max_radius_y * math.sin(angle))

            # Clamp to grid bounds
            rx = max(1, min(width - 2, rx))
            ry = max(1, min(height - 2, ry))

            positions.append((rx, ry))

        return positions

    def _draw_tendrils(
        self, grid: List[List[str]], cx: int, cy: int, positions: List[Tuple[int, int]]
    ) -> None:
        """
        Draw vine-like tendrils from core to each node.
        Uses Bresenham-style line drawing with organic glyphs.
        """
        for nx, ny in positions:
            self._draw_tendril_line(grid, cx, cy, nx, ny)

    def _draw_tendril_line(self, grid: List[List[str]], x0: int, y0: int, x1: int, y1: int) -> None:
        """Draw a single tendril from (x0,y0) to (x1,y1)."""
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        x, y = x0, y0
        steps = 0
        max_steps = dx + dy + 1

        while steps < max_steps:
            # Don't overwrite core or endpoints
            if (x, y) != (x0, y0) and (x, y) != (x1, y1):
                if 0 <= x < len(grid[0]) and 0 <= y < len(grid):
                    # Choose tendril glyph based on direction
                    glyph = self._tendril_glyph(x - x0, y - y0, sx, sy)
                    # Only draw if cell is empty
                    if grid[y][x] == GLYPHS["empty"]:
                        grid[y][x] = glyph

            if x == x1 and y == y1:
                break

            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy

            steps += 1

    def _tendril_glyph(self, dx: int, dy: int, sx: int, sy: int) -> str:
        """Choose tendril glyph based on direction."""
        # Diagonal movement
        if sx != 0 and sy != 0:
            if sx == sy:
                return GLYPHS["tendril_dr"]  # ╲
            else:
                return GLYPHS["tendril_dl"]  # ╱
        # Horizontal
        if sy == 0:
            return GLYPHS["tendril_h"]  # ─
        # Vertical
        return GLYPHS["tendril_v"]  # │

    def _draw_rifts(self, grid: List[List[str]], width: int, height: int) -> None:
        """
        Draw contradiction rifts as scar lines.
        Each contradiction creates a horizontal scar.
        """
        num_rifts = min(3, len(self.state.contradictions))

        for i in range(num_rifts):
            # Position rifts in different rows
            y = (height // 4) + (i * (height // 3))
            y = max(1, min(height - 2, y))

            # Draw rift scar across partial width
            start_x = 4 + (i * 3)
            end_x = width - 4 - (i * 2)

            for x in range(start_x, end_x):
                # Jagged pattern
                if (x + i) % 3 == 0:
                    if 0 <= y < height and 0 <= x < width:
                        grid[y][x] = GLYPHS["rift"]

    def _draw_pulse_ring(
        self, grid: List[List[str]], cx: int, cy: int, width: int, height: int
    ) -> None:
        """Draw a subtle pulse ring around the core."""
        # Small ring of dots around core
        offsets = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        pulse_active = self._tick % 8 < 4

        if pulse_active:
            for dx, dy in offsets:
                x, y = cx + dx, cy + dy
                if 0 <= x < width and 0 <= y < height:
                    if grid[y][x] == GLYPHS["empty"]:
                        grid[y][x] = GLYPHS["pulse_ring"]

    # ============================================================
    # NODE HELPERS
    # ============================================================

    def _node_glyph(self, node: Node) -> str:
        """Get glyph for a node based on type."""
        if node.node_type == "fact":
            return GLYPHS["fact"]
        if node.node_type == "belief":
            return GLYPHS["belief"]
        if node.node_type == "hypothesis":
            return GLYPHS["hypothesis"]
        return GLYPHS["tendril_node"]

    def _glyph_style(self, char: str) -> str:
        """Get Rich style for a glyph character."""
        style_map = {
            GLYPHS["core"]: VECNA_STYLES["warning"],
            GLYPHS["core_pulse"]: VECNA_STYLES["error"],
            GLYPHS["fact"]: VECNA_STYLES["fact"],
            GLYPHS["belief"]: VECNA_STYLES["belief"],
            GLYPHS["hypothesis"]: VECNA_STYLES["hypothesis"],
            GLYPHS["rift"]: VECNA_STYLES["contradiction"],
            GLYPHS["tendril_h"]: VECNA_STYLES["muted"],
            GLYPHS["tendril_v"]: VECNA_STYLES["muted"],
            GLYPHS["tendril_dr"]: VECNA_STYLES["muted"],
            GLYPHS["tendril_dl"]: VECNA_STYLES["muted"],
            GLYPHS["tendril_node"]: VECNA_STYLES["dim"],
            GLYPHS["pulse_ring"]: VECNA_STYLES["glow"],
        }
        return style_map.get(char, VECNA_STYLES["dim"])

    def _collect_nodes(self) -> List[Node]:
        """Collect all nodes from state, ordered by insertion (oldest first)."""
        nodes: List[Node] = []
        idx = 0

        # Interleave for visual variety
        facts = list(self.state.facts[-15:])
        beliefs = list(self.state.beliefs[-10:])
        hypotheses = list(self.state.hypotheses[-8:])

        # Merge by creation order (approximate by list order)
        all_items = []
        for fact in facts:
            all_items.append(("fact", fact))
        for belief in beliefs:
            all_items.append(("belief", belief))
        for hyp in hypotheses:
            all_items.append(("hypothesis", hyp))

        # Sort by id to approximate insertion order
        all_items.sort(key=lambda x: x[1].id)

        for node_type, item in all_items:
            nodes.append(
                Node(
                    id=item.id,
                    label=item.content,
                    node_type=node_type,
                    confidence=item.confidence,
                    source=item.source_model,
                    index=idx,
                )
            )
            idx += 1

        return nodes

    def _coherence_score(self) -> float:
        """Compute coherence score for the substrate."""
        total = len(self.state.facts) + len(self.state.beliefs) + len(self.state.hypotheses)
        if total == 0:
            return 0.42
        contradictions = len(self.state.contradictions)
        score = max(0.1, min(1.0, 1.0 - (contradictions / (total + 1))))
        return score

    def _node_count(self) -> int:
        """Total node count in substrate."""
        return len(self.state.facts) + len(self.state.beliefs) + len(self.state.hypotheses)
