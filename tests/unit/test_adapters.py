"""
Unit tests for Model Adapters.

Tests:
- ModelConfig creation
- BaseAdapter methods (prompt building, update parsing)
- Adapter factory
- HIVE_UPDATE parsing
"""

import pytest
from datetime import datetime

from vecna.adapters.base import (
    ModelConfig,
    BaseAdapter,
    HIVE_IDENTITY_PROMPT,
    OllamaAdapter,
    TransformersAdapter,
    GroqAdapter,
    CopilotAdapter,
    create_adapter,
)
from vecna.core.hive_state import HiveState
from vecna.core.types import HiveUpdate


class TestModelConfig:
    """Tests for ModelConfig dataclass."""

    def test_default_config(self):
        """Test default ModelConfig values."""
        config = ModelConfig(name="test", model_id="gpt-4")

        assert config.name == "test"
        assert config.model_id == "gpt-4"
        assert config.domain == "general"
        assert config.weight == 1.0
        assert config.temperature == 0.7
        assert config.max_tokens == 4096
        assert config.extra_params == {}

    def test_custom_config(self):
        """Test custom ModelConfig values."""
        config = ModelConfig(
            name="code-expert",
            model_id="gpt-4o",
            domain="code",
            weight=1.5,
            temperature=0.3,
            max_tokens=8192,
            persona="You are a Python expert.",
        )

        assert config.domain == "code"
        assert config.weight == 1.5
        assert config.temperature == 0.3
        assert config.persona == "You are a Python expert."


class TestBaseAdapterPromptBuilding:
    """Tests for prompt building in BaseAdapter."""

    @pytest.fixture
    def mock_adapter(self, model_config):
        """Create a mock adapter for testing."""

        class MockAdapter(BaseAdapter):
            async def generate(self, prompt: str) -> str:
                return "Mock response"

        return MockAdapter(model_config)

    def test_get_system_message_default(self, mock_adapter):
        """Test default system message."""
        msg = mock_adapter.get_system_message()

        assert "Hive" in msg

    def test_get_system_message_with_persona(self, model_config):
        """Test system message with persona."""
        model_config.persona = "You are a quantum physicist."

        class MockAdapter(BaseAdapter):
            async def generate(self, prompt: str) -> str:
                return ""

        adapter = MockAdapter(model_config)
        msg = adapter.get_system_message()

        assert "quantum physicist" in msg
        assert "STYLE" in msg

    def test_build_prompt(self, mock_adapter, clean_state):
        """Test building full prompt with state."""
        prompt = mock_adapter.build_prompt(clean_state, "Test task")

        assert "VECNA" in prompt
        assert "Test task" in prompt
        assert "HIVE_UPDATE" in prompt

    def test_prompt_includes_memory_context(self, mock_adapter, populated_state):
        """Test that prompt includes memory context."""
        prompt = mock_adapter.build_prompt(populated_state, "Analyze this")

        # Should include some facts from state
        assert len(prompt) > 500  # Should be substantial


class TestHiveUpdateParsing:
    """Tests for parsing HIVE_UPDATE from model output."""

    @pytest.fixture
    def mock_adapter(self, model_config):
        """Create a mock adapter for testing."""

        class MockAdapter(BaseAdapter):
            async def generate(self, prompt: str) -> str:
                return ""

        return MockAdapter(model_config)

    def test_parse_empty_output(self, mock_adapter):
        """Test parsing output without HIVE_UPDATE block."""
        output = "This is just a regular response without any update."

        update = mock_adapter.parse_update(output)

        assert update.source_model == "test-model"
        assert update.new_facts == []
        assert update.belief_changes == []

    def test_parse_complete_update(self, mock_adapter):
        """Test parsing a complete HIVE_UPDATE block."""
        output = """
Here is my response.

<HIVE_UPDATE>
new_facts:
- content: "Python is interpreted"
  confidence: 0.9
  domain: "code"

belief_changes:
- content: "Testing improves quality"
  confidence: 0.8
  reasoning: "Empirical evidence"

hypotheses:
- content: "Could optimize with caching"
  confidence: 0.4
  notes: "Needs testing"

open_questions:
- question: "What is the best approach?"
  priority: "high"

overall_confidence: 0.85
</HIVE_UPDATE>
"""

        update = mock_adapter.parse_update(output)

        assert len(update.new_facts) == 1
        assert update.new_facts[0]["content"] == "Python is interpreted"
        assert len(update.belief_changes) == 1
        assert len(update.new_hypotheses) == 1
        assert len(update.open_questions) == 1
        assert update.confidence == 0.85

    def test_parse_update_with_contradictions(self, mock_adapter):
        """Test parsing update with contradictions."""
        output = """
<HIVE_UPDATE>
contradictions:
- item_a: "The sky is blue"
  item_b: "The sky is green"

overall_confidence: 0.5
</HIVE_UPDATE>
"""

        update = mock_adapter.parse_update(output)

        assert len(update.contradictions_found) == 1

    def test_parse_empty_update_block(self, mock_adapter):
        """Test parsing empty HIVE_UPDATE block."""
        output = """
Just a response.

<HIVE_UPDATE></HIVE_UPDATE>
"""

        update = mock_adapter.parse_update(output)

        assert update.new_facts == []
        assert update.belief_changes == []

    def test_parse_malformed_update(self, mock_adapter):
        """Test parsing malformed HIVE_UPDATE block."""
        output = """
<HIVE_UPDATE>
new_facts:
- this is not valid yaml
overall_confidence: not_a_number
</HIVE_UPDATE>
"""

        # Should not crash, just return partial/empty update
        update = mock_adapter.parse_update(output)

        assert update is not None


class TestAdapterFactory:
    """Tests for create_adapter factory function."""

    def test_create_ollama_adapter(self):
        """Test creating Ollama adapter for local models."""
        config = ModelConfig(
            name="local-llama", model_id="llama3.2", base_url="http://localhost:11434"
        )

        adapter = create_adapter(config)

        assert isinstance(adapter, OllamaAdapter)

    @pytest.mark.skip(reason="Groq adapter not used currently")
    def test_create_groq_adapter(self):
        """Test creating Groq adapter."""
        config = ModelConfig(
            name="groq-model",
            model_id="llama3-70b-8192",
            base_url="https://api.groq.com",
            extra_params={"provider": "groq"},
        )

        adapter = create_adapter(config)

        assert isinstance(adapter, GroqAdapter)

    def test_create_copilot_adapter_default(self):
        """Test that default adapter is Copilot."""
        config = ModelConfig(name="gpt-4", model_id="gpt-4o")

        adapter = create_adapter(config)

        assert isinstance(adapter, CopilotAdapter)

    def test_create_transformers_adapter(self):
        """Test creating Transformers adapter for local models."""
        config = ModelConfig(
            name="local-mistral",
            model_id="mistralai/Mistral-7B",
            # No base_url means use transformers
        )

        adapter = create_adapter(config)

        assert isinstance(adapter, TransformersAdapter)


class TestOllamaAdapter:
    """Tests for OllamaAdapter initialization."""

    def test_ollama_adapter_init(self, model_config):
        """Test Ollama adapter initialization."""
        model_config.base_url = "http://localhost:11434"

        adapter = OllamaAdapter(model_config)

        assert adapter.base_url == "http://localhost:11434"

    def test_ollama_adapter_default_url(self, model_config):
        """Test Ollama adapter uses default URL."""
        model_config.base_url = None

        adapter = OllamaAdapter(model_config)

        assert adapter.base_url == "http://localhost:11434"


class TestGroqAdapter:
    """Tests for GroqAdapter initialization."""

    def test_groq_adapter_init(self, model_config):
        """Test Groq adapter initialization."""
        model_config.api_key = "test-key"

        adapter = GroqAdapter(model_config)

        assert adapter.config.api_key == "test-key"


class TestCopilotAdapter:
    """Tests for CopilotAdapter initialization."""

    def test_copilot_adapter_init(self, model_config):
        """Test Copilot adapter initialization."""
        adapter = CopilotAdapter(model_config)

        assert adapter.COPILOT_CHAT_URL == "https://api.githubcopilot.com/chat/completions"


class TestHiveIdentityPrompt:
    """Tests for the HIVE_IDENTITY_PROMPT template."""

    def test_prompt_contains_placeholders(self):
        """Test that prompt template has required placeholders."""
        assert "{memory_context}" in HIVE_IDENTITY_PROMPT
        assert "{task}" in HIVE_IDENTITY_PROMPT

    def test_prompt_contains_identity(self):
        """Test that prompt contains identity information."""
        assert "VECNA" in HIVE_IDENTITY_PROMPT
        assert "LightningEmperor" in HIVE_IDENTITY_PROMPT

    def test_prompt_contains_update_format(self):
        """Test that prompt contains update format instructions."""
        assert "HIVE_UPDATE" in HIVE_IDENTITY_PROMPT
        assert "new_facts" in HIVE_IDENTITY_PROMPT
        assert "belief_changes" in HIVE_IDENTITY_PROMPT
