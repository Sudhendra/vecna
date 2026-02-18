"""Vecna Textual TUI application.

Provides a full terminal UI with:
- Conversation pane for interactive chat with streaming
- Substrate visualizer sidebar showing facts, beliefs, goals
- Integration and channel status indicators
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vecna.tui.app")

try:
    from textual.app import App, ComposeResult
    from textual.containers import Horizontal
    from textual.widgets import Footer, Header, Input, Static

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False
    logger.debug("textual not installed, TUI unavailable")


class SubstratePanel:
    """Sidebar panel showing HiveState substrate overview.

    Displays counts of facts, beliefs, goals, and overall
    coherence metrics. Updates in real-time as state changes.
    """

    def __init__(self) -> None:
        self.facts_count: int = 0
        self.beliefs_count: int = 0
        self.goals_count: int = 0
        self.coherence: float = 0.0

    def update_state(
        self,
        facts_count: int = 0,
        beliefs_count: int = 0,
        goals_count: int = 0,
        coherence: float = 0.0,
    ) -> None:
        """Update substrate panel state.

        Args:
            facts_count: Number of facts in state.
            beliefs_count: Number of beliefs in state.
            goals_count: Number of goals in state.
            coherence: Overall state coherence score.
        """
        self.facts_count = facts_count
        self.beliefs_count = beliefs_count
        self.goals_count = goals_count
        self.coherence = coherence

    def render_content(self) -> str:
        """Render substrate state as a text summary.

        Returns:
            Formatted string showing state counts.
        """
        lines = [
            "╔═══ Substrate ═══╗",
            f"║ Facts:   {self.facts_count:>6} ║",
            f"║ Beliefs: {self.beliefs_count:>6} ║",
            f"║ Goals:   {self.goals_count:>6} ║",
            f"║ Cohere:  {self.coherence:>5.1%} ║",
            "╚═════════════════╝",
        ]
        return "\n".join(lines)


class ConversationPane:
    """Main conversation display pane.

    Maintains a list of chat messages and renders them
    for display in the TUI.
    """

    def __init__(self) -> None:
        self.messages: List[Dict[str, str]] = []

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation.

        Args:
            role: Message role (user or assistant).
            content: Message text content.
        """
        self.messages.append(
            {
                "role": role,
                "content": content,
            }
        )

    def render_messages(self) -> str:
        """Render all messages as formatted text.

        Returns:
            String with all messages formatted for display.
        """
        lines = []
        for msg in self.messages:
            prefix = "You" if msg["role"] == "user" else "Vecna"
            lines.append(f"[{prefix}] {msg['content']}")
        return "\n".join(lines)


class VecnaTUI:
    """Main Textual TUI application for Vecna.

    Composes a conversation pane with a substrate sidebar
    and provides input handling for interactive chat.
    """

    CSS = """
    #substrate {
        width: 24;
        dock: right;
    }
    #conversation {
        width: 1fr;
    }
    """
    CSS_PATH: Optional[str] = None
    title = "Vecna"

    def __init__(self) -> None:
        self.substrate_panel = SubstratePanel()
        self.conversation_pane = ConversationPane()
        self._hive_loop: Any = None

    def set_hive_loop(self, loop: Any) -> None:
        """Attach a HiveLoop to the TUI.

        Args:
            loop: HiveLoop instance for processing messages.
        """
        self._hive_loop = loop

    async def handle_input(self, text: str) -> str:
        """Handle user input text.

        Args:
            text: User's input message.

        Returns:
            Response from HiveLoop or fallback message.
        """
        self.conversation_pane.add_message("user", text)
        response = ""
        if self._hive_loop is not None:
            response = await self._hive_loop.think(text)
        else:
            response = "HiveLoop not connected."
        self.conversation_pane.add_message("assistant", response)
        return response

    def run(self) -> None:
        """Launch the Textual TUI application.

        Requires textual to be installed. Wraps the Textual App
        and starts the event loop.
        """
        if not TEXTUAL_AVAILABLE:
            raise ImportError(
                "textual is required for the TUI. Install with: pip install textual trogon"
            )

        app = _VecnaTextualApp(vecna_tui=self)
        app.run()


if TEXTUAL_AVAILABLE:

    class _VecnaTextualApp(App):  # type: ignore[misc]
        """Internal Textual App wrapper.

        This is the actual Textual application that renders the TUI.
        It delegates state management to VecnaTUI.
        """

        TITLE = "Vecna"
        CSS = """
        #substrate {
            width: 24;
            dock: right;
        }
        #conversation {
            width: 1fr;
        }
        """

        def __init__(self, vecna_tui: "VecnaTUI") -> None:
            super().__init__()
            self._vecna_tui = vecna_tui

        def compose(self) -> ComposeResult:
            """Compose the TUI layout."""
            yield Header()
            with Horizontal():
                yield Static(
                    self._vecna_tui.conversation_pane.render_messages(),
                    id="conversation",
                )
                yield Static(
                    self._vecna_tui.substrate_panel.render_content(),
                    id="substrate",
                )
            yield Input(placeholder="Type your message...")
            yield Footer()
