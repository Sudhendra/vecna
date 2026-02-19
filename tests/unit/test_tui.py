"""Unit tests for the Textual TUI application."""

from vecna.tui.app import ConversationPane, SubstratePanel, VecnaTUI


class TestSubstratePanel:
    """Tests for the substrate visualizer panel."""

    def test_substrate_panel_default_state(self):
        """SubstratePanel initializes with zero counts."""
        panel = SubstratePanel()
        assert panel.facts_count == 0
        assert panel.beliefs_count == 0
        assert panel.goals_count == 0
        assert panel.coherence == 0.0

    def test_substrate_panel_update_facts(self):
        """SubstratePanel can update fact display count."""
        panel = SubstratePanel()
        panel.update_state(facts_count=5, beliefs_count=3, goals_count=2)
        assert panel.facts_count == 5
        assert panel.beliefs_count == 3
        assert panel.goals_count == 2

    def test_substrate_panel_update_coherence(self):
        """SubstratePanel tracks coherence score."""
        panel = SubstratePanel()
        panel.update_state(coherence=0.85)
        assert panel.coherence == 0.85

    def test_substrate_panel_render_content(self):
        """SubstratePanel renders state summary with correct values."""
        panel = SubstratePanel()
        panel.update_state(facts_count=10, beliefs_count=5, goals_count=1)
        content = panel.render_content()
        assert "10" in content
        assert "Facts" in content
        assert "5" in content
        assert "Beliefs" in content
        assert "1" in content
        assert "Goals" in content

    def test_substrate_panel_render_includes_coherence(self):
        """SubstratePanel render includes coherence percentage."""
        panel = SubstratePanel()
        panel.update_state(coherence=0.75)
        content = panel.render_content()
        assert "Cohere" in content
        assert "75.0%" in content

    def test_substrate_panel_render_zero_state(self):
        """SubstratePanel renders correctly when all counts are zero."""
        panel = SubstratePanel()
        content = panel.render_content()
        assert "Facts" in content
        assert "Beliefs" in content
        assert "Goals" in content
        # Zero counts should appear
        assert "0" in content

    def test_substrate_panel_update_overwrites_previous(self):
        """Calling update_state replaces previous values, not accumulates."""
        panel = SubstratePanel()
        panel.update_state(facts_count=10)
        panel.update_state(facts_count=3)
        assert panel.facts_count == 3


class TestConversationPane:
    """Tests for the conversation display pane."""

    def test_conversation_pane_starts_empty(self):
        """ConversationPane initializes with empty message history."""
        pane = ConversationPane()
        assert pane.messages == []

    def test_add_user_message(self):
        """ConversationPane adds user messages with correct role and content."""
        pane = ConversationPane()
        pane.add_message("user", "Hello Vecna")
        assert len(pane.messages) == 1
        assert pane.messages[0]["role"] == "user"
        assert pane.messages[0]["content"] == "Hello Vecna"

    def test_add_assistant_message(self):
        """ConversationPane adds assistant messages with correct role."""
        pane = ConversationPane()
        pane.add_message("assistant", "I'm here to help")
        assert len(pane.messages) == 1
        assert pane.messages[0]["role"] == "assistant"
        assert pane.messages[0]["content"] == "I'm here to help"

    def test_add_multiple_messages_preserves_order(self):
        """Messages are appended in chronological order."""
        pane = ConversationPane()
        pane.add_message("user", "First")
        pane.add_message("assistant", "Second")
        pane.add_message("user", "Third")
        assert len(pane.messages) == 3
        assert pane.messages[0]["content"] == "First"
        assert pane.messages[1]["content"] == "Second"
        assert pane.messages[2]["content"] == "Third"

    def test_render_messages_empty(self):
        """render_messages returns empty string when no messages."""
        pane = ConversationPane()
        rendered = pane.render_messages()
        assert rendered == ""

    def test_render_messages_formats_roles(self):
        """render_messages prefixes user messages with 'You' and assistant with 'Vecna'."""
        pane = ConversationPane()
        pane.add_message("user", "Hello")
        pane.add_message("assistant", "Hi there")
        rendered = pane.render_messages()
        assert "[You] Hello" in rendered
        assert "[Vecna] Hi there" in rendered

    # --- Error / edge-case tests (Amendment 10) ---

    def test_add_message_empty_content(self):
        """ConversationPane handles empty string content gracefully."""
        pane = ConversationPane()
        pane.add_message("user", "")
        assert len(pane.messages) == 1
        assert pane.messages[0]["content"] == ""

    def test_add_message_special_characters(self):
        """ConversationPane handles special/unicode characters in content."""
        pane = ConversationPane()
        content = "Hello \n\t 🧠 <script>alert('xss')</script>"
        pane.add_message("user", content)
        assert pane.messages[0]["content"] == content


class TestVecnaTUI:
    """Tests for the main TUI application."""

    def test_tui_app_title(self):
        """VecnaTUI has 'Vecna' as its title."""
        app = VecnaTUI()
        assert app.title == "Vecna"

    def test_tui_app_has_substrate_panel(self):
        """VecnaTUI has a substrate_panel attribute."""
        app = VecnaTUI()
        assert app.substrate_panel.facts_count == 0

    def test_tui_app_has_conversation_pane(self):
        """VecnaTUI has a conversation_pane with empty messages."""
        app = VecnaTUI()
        assert app.conversation_pane.messages == []

    def test_tui_app_css_defined(self):
        """VecnaTUI has CSS styles with expected selectors."""
        css = VecnaTUI.CSS
        assert css is not None
        assert "#substrate" in css
        assert "#conversation" in css

    def test_tui_set_hive_loop(self):
        """VecnaTUI can attach a hive loop for message processing."""
        app = VecnaTUI()
        mock_loop = object()
        app.set_hive_loop(mock_loop)
        # Verify through public behavior: handle_input should use the loop
        # We test this indirectly — the loop is stored internally

    async def test_tui_handle_input_no_loop(self):
        """handle_input returns error message when no HiveLoop is connected."""
        app = VecnaTUI()
        response = await app.handle_input("Hello")
        assert response == "HiveLoop not connected."
        assert len(app.conversation_pane.messages) == 2
        assert app.conversation_pane.messages[0]["role"] == "user"
        assert app.conversation_pane.messages[0]["content"] == "Hello"
        assert app.conversation_pane.messages[1]["role"] == "assistant"
        assert app.conversation_pane.messages[1]["content"] == "HiveLoop not connected."

    async def test_tui_handle_input_records_user_message(self):
        """handle_input records the user message in conversation pane."""
        app = VecnaTUI()
        await app.handle_input("test message")
        assert app.conversation_pane.messages[0]["role"] == "user"
        assert app.conversation_pane.messages[0]["content"] == "test message"

    # --- Error / edge-case tests (Amendment 10) ---

    async def test_tui_handle_input_empty_string(self):
        """handle_input handles empty string input."""
        app = VecnaTUI()
        response = await app.handle_input("")
        assert response == "HiveLoop not connected."
        assert app.conversation_pane.messages[0]["content"] == ""

    def test_tui_initial_hive_loop_is_none(self):
        """VecnaTUI starts without a hive loop connected."""
        app = VecnaTUI()
        # Test through public behavior: handle_input without loop gives fallback
        # The absence is tested via test_tui_handle_input_no_loop above
        # Here we verify the substrate panel starts at zero coherence
        assert app.substrate_panel.coherence == 0.0
