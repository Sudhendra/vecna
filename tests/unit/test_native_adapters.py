"""Unit tests for native OpenAI and Anthropic adapters.

Tests cover initialization, API key handling, generation, tool calling,
streaming, error paths (Amendment 10: 4+ error tests per externally-facing
adapter), and factory routing.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from vecna.adapters.base import ModelConfig, create_adapter
from vecna.adapters.openai_adapter import OpenAIAdapter
from vecna.adapters.anthropic_adapter import AnthropicAdapter
from vecna.core.types import HiveUpdate


# ============================================================
# OpenAI Adapter Tests
# ============================================================


class TestOpenAIAdapter:
    """Tests for the OpenAI native adapter."""

    def test_openai_adapter_init(self):
        """OpenAIAdapter initializes with ModelConfig and stores config correctly."""
        config = ModelConfig(
            name="openai-gpt4",
            model_id="gpt-4-turbo",
            api_key="sk-test-key",
        )
        adapter = OpenAIAdapter(config)
        assert adapter.config.name == "openai-gpt4"
        assert adapter.config.model_id == "gpt-4-turbo"
        assert adapter._get_provider_name() == "openai"
        assert adapter._api_key == "sk-test-key"

    def test_openai_adapter_requires_api_key(self):
        """OpenAIAdapter raises ValueError if no API key available."""
        config = ModelConfig(name="openai", model_id="gpt-4-turbo")
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="API key"):
                OpenAIAdapter(config)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test-from-env"})
    def test_openai_adapter_uses_env_key(self):
        """OpenAIAdapter falls back to OPENAI_API_KEY env var."""
        config = ModelConfig(name="openai", model_id="gpt-4-turbo")
        adapter = OpenAIAdapter(config)
        assert adapter._api_key == "sk-test-from-env"

    async def test_openai_generate_calls_sdk(self):
        """OpenAIAdapter.generate calls OpenAI chat completions and returns text."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
            temperature=0.7,
            max_tokens=1000,
        )
        adapter = OpenAIAdapter(config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello from GPT-4"
        mock_response.choices[0].message.tool_calls = None
        mock_response.usage = MagicMock(
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )

        adapter._client = MagicMock()
        adapter._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await adapter.generate("Test prompt")
        assert result == "Hello from GPT-4"

        # Verify the SDK was called with correct parameters
        call_kwargs = adapter._client.chat.completions.create.call_args
        assert call_kwargs.kwargs["model"] == "gpt-4-turbo"
        assert call_kwargs.kwargs["temperature"] == 0.7
        assert call_kwargs.kwargs["max_tokens"] == 1000

    async def test_openai_generate_with_tool_calls(self):
        """OpenAIAdapter returns tool call JSON when model uses hive_update tool."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
        )
        adapter = OpenAIAdapter(config)

        tool_args = {
            "new_facts": [{"content": "Test fact", "confidence": 0.9}],
            "belief_changes": [],
            "hypotheses": [],
            "overall_confidence": 0.85,
        }
        tool_call = MagicMock()
        tool_call.function.name = "hive_update"
        tool_call.function.arguments = json.dumps(tool_args)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.choices[0].message.tool_calls = [tool_call]
        mock_response.usage = MagicMock(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )

        adapter._client = MagicMock()
        adapter._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await adapter.generate("Test")
        parsed = json.loads(result)
        assert parsed["new_facts"][0]["content"] == "Test fact"
        assert parsed["overall_confidence"] == 0.85

    async def test_openai_parse_update_from_tool_json(self):
        """OpenAIAdapter.parse_update produces HiveUpdate with correct fields."""
        config = ModelConfig(
            name="openai-gpt4",
            model_id="gpt-4-turbo",
            api_key="sk-test",
        )
        adapter = OpenAIAdapter(config)

        tool_json = json.dumps(
            {
                "new_facts": [{"content": "Earth orbits Sun", "confidence": 0.99}],
                "belief_changes": [{"content": "Science is useful", "confidence": 0.8}],
                "overall_confidence": 0.95,
            }
        )

        update = adapter.parse_update(tool_json)
        assert isinstance(update, HiveUpdate)
        assert len(update.new_facts) == 1
        assert update.new_facts[0]["content"] == "Earth orbits Sun"
        assert update.source_model == "openai-gpt4"
        assert update.confidence == 0.95

    async def test_openai_streaming_generates_chunks(self):
        """OpenAIAdapter supports streaming via generate_stream."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
        )
        adapter = OpenAIAdapter(config)

        async def mock_stream():
            for text in ["Hello", " world", "!"]:
                chunk = MagicMock()
                chunk.choices = [MagicMock()]
                chunk.choices[0].delta.content = text
                chunk.choices[0].delta.tool_calls = None
                yield chunk

        adapter._client = MagicMock()
        adapter._client.chat.completions.create = AsyncMock(return_value=mock_stream())

        chunks = []
        async for chunk in adapter.generate_stream("Test"):
            chunks.append(chunk)
        assert "".join(chunks) == "Hello world!"

    # ---- Amendment 10: 4+ error path tests for externally-facing adapter ----

    async def test_openai_rate_limit_error(self):
        """OpenAIAdapter handles 429 rate limit errors gracefully."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
        )
        adapter = OpenAIAdapter(config)

        # Simulate openai.RateLimitError
        from openai import RateLimitError

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        error = RateLimitError(
            message="Rate limit exceeded",
            response=mock_response,
            body={"error": {"message": "Rate limit exceeded"}},
        )

        adapter._client = MagicMock()
        adapter._client.chat.completions.create = AsyncMock(side_effect=error)

        with pytest.raises(RateLimitError, match="Rate limit"):
            await adapter.generate("Test")

    async def test_openai_timeout_error(self):
        """OpenAIAdapter handles timeout errors without crashing."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
        )
        adapter = OpenAIAdapter(config)

        from openai import APITimeoutError

        error = APITimeoutError(request=MagicMock())

        adapter._client = MagicMock()
        adapter._client.chat.completions.create = AsyncMock(side_effect=error)

        with pytest.raises(APITimeoutError):
            await adapter.generate("Test")

    async def test_openai_authentication_error(self):
        """OpenAIAdapter handles 401 authentication failures."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-invalid",
        )
        adapter = OpenAIAdapter(config)

        from openai import AuthenticationError

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        error = AuthenticationError(
            message="Invalid API key",
            response=mock_response,
            body={"error": {"message": "Invalid API key"}},
        )

        adapter._client = MagicMock()
        adapter._client.chat.completions.create = AsyncMock(side_effect=error)

        with pytest.raises(AuthenticationError, match="Invalid API key"):
            await adapter.generate("Test")

    async def test_openai_context_length_exceeded(self):
        """OpenAIAdapter handles context length exceeded (400 error)."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
        )
        adapter = OpenAIAdapter(config)

        from openai import BadRequestError

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.headers = {}
        error = BadRequestError(
            message="maximum context length exceeded",
            response=mock_response,
            body={"error": {"message": "maximum context length exceeded"}},
        )

        adapter._client = MagicMock()
        adapter._client.chat.completions.create = AsyncMock(side_effect=error)

        with pytest.raises(BadRequestError, match="context length"):
            await adapter.generate("Test")

    async def test_openai_parse_update_malformed_json(self):
        """OpenAIAdapter.parse_update handles malformed JSON gracefully."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
        )
        adapter = OpenAIAdapter(config)

        # Malformed JSON — should fall back to YAML parse or return empty update
        update = adapter.parse_update("not valid json {{{")
        assert isinstance(update, HiveUpdate)
        assert update.source_model == "openai"

    async def test_openai_generate_empty_response(self):
        """OpenAIAdapter handles empty content from API."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
        )
        adapter = OpenAIAdapter(config)

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None
        mock_response.choices[0].message.tool_calls = None
        mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=0, total_tokens=10)

        adapter._client = MagicMock()
        adapter._client.chat.completions.create = AsyncMock(return_value=mock_response)

        result = await adapter.generate("Test")
        assert result == ""


# ============================================================
# Anthropic Adapter Tests
# ============================================================


class TestAnthropicAdapter:
    """Tests for the Anthropic native adapter."""

    def test_anthropic_adapter_init(self):
        """AnthropicAdapter initializes with ModelConfig and stores config correctly."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)
        assert adapter.config.name == "claude"
        assert adapter.config.model_id == "claude-3-sonnet-20240229"
        assert adapter._get_provider_name() == "anthropic"
        assert adapter._api_key == "sk-ant-test"

    def test_anthropic_adapter_requires_api_key(self):
        """AnthropicAdapter raises ValueError if no API key available."""
        config = ModelConfig(name="claude", model_id="claude-3-sonnet-20240229")
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="API key"):
                AnthropicAdapter(config)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-from-env"})
    def test_anthropic_adapter_uses_env_key(self):
        """AnthropicAdapter falls back to ANTHROPIC_API_KEY env var."""
        config = ModelConfig(name="claude", model_id="claude-3-sonnet-20240229")
        adapter = AnthropicAdapter(config)
        assert adapter._api_key == "sk-ant-from-env"

    async def test_anthropic_generate_calls_sdk(self):
        """AnthropicAdapter.generate calls Anthropic messages API and returns text."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
            temperature=0.7,
            max_tokens=1000,
        )
        adapter = AnthropicAdapter(config)

        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Hello from Claude"

        mock_response = MagicMock()
        mock_response.content = [text_block]
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(
            input_tokens=10,
            output_tokens=5,
        )

        adapter._client = MagicMock()
        adapter._client.messages.create = AsyncMock(return_value=mock_response)

        result = await adapter.generate("Test prompt")
        assert result == "Hello from Claude"

        # Verify the SDK was called with correct parameters
        call_kwargs = adapter._client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "claude-3-sonnet-20240229"
        assert call_kwargs.kwargs["max_tokens"] == 1000

    async def test_anthropic_generate_with_tool_use(self):
        """AnthropicAdapter handles tool_use content blocks."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)

        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "hive_update"
        tool_block.input = {
            "new_facts": [{"content": "Claude fact", "confidence": 0.85}],
            "belief_changes": [],
            "overall_confidence": 0.9,
        }

        mock_response = MagicMock()
        mock_response.content = [tool_block]
        mock_response.stop_reason = "tool_use"
        mock_response.usage = MagicMock(
            input_tokens=15,
            output_tokens=25,
        )

        adapter._client = MagicMock()
        adapter._client.messages.create = AsyncMock(return_value=mock_response)

        result = await adapter.generate("Test")
        parsed = json.loads(result)
        assert parsed["new_facts"][0]["content"] == "Claude fact"
        assert parsed["overall_confidence"] == 0.9

    async def test_anthropic_parse_update_from_tool_json(self):
        """AnthropicAdapter.parse_update produces HiveUpdate with correct fields."""
        config = ModelConfig(
            name="claude-sonnet",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)

        tool_json = json.dumps(
            {
                "new_facts": [{"content": "Water is H2O", "confidence": 0.99}],
                "belief_changes": [],
                "overall_confidence": 0.92,
            }
        )

        update = adapter.parse_update(tool_json)
        assert isinstance(update, HiveUpdate)
        assert len(update.new_facts) == 1
        assert update.new_facts[0]["content"] == "Water is H2O"
        assert update.source_model == "claude-sonnet"
        assert update.confidence == 0.92

    async def test_anthropic_streaming_generates_chunks(self):
        """AnthropicAdapter supports streaming via generate_stream."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)

        async def mock_stream():
            for text in ["Bonjour", " le", " monde"]:
                event = MagicMock()
                event.type = "content_block_delta"
                event.delta = MagicMock()
                event.delta.type = "text_delta"
                event.delta.text = text
                yield event

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_stream())
        mock_context.__aexit__ = AsyncMock(return_value=False)

        adapter._client = MagicMock()
        adapter._client.messages.stream = MagicMock(return_value=mock_context)

        chunks = []
        async for chunk in adapter.generate_stream("Test"):
            chunks.append(chunk)
        assert "".join(chunks) == "Bonjour le monde"

    # ---- Amendment 10: 4+ error path tests for externally-facing adapter ----

    async def test_anthropic_invalid_api_key(self):
        """AnthropicAdapter handles 401 authentication failures with clear error."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-invalid",
        )
        adapter = AnthropicAdapter(config)

        from anthropic import AuthenticationError

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}
        error = AuthenticationError(
            message="Invalid API key",
            response=mock_response,
            body={"error": {"message": "Invalid API key"}},
        )

        adapter._client = MagicMock()
        adapter._client.messages.create = AsyncMock(side_effect=error)

        with pytest.raises(AuthenticationError, match="Invalid API key"):
            await adapter.generate("Test")

    async def test_anthropic_rate_limit_error(self):
        """AnthropicAdapter handles 429 rate limit errors."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)

        from anthropic import RateLimitError

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        error = RateLimitError(
            message="Rate limit exceeded",
            response=mock_response,
            body={"error": {"message": "Rate limit exceeded"}},
        )

        adapter._client = MagicMock()
        adapter._client.messages.create = AsyncMock(side_effect=error)

        with pytest.raises(RateLimitError, match="Rate limit"):
            await adapter.generate("Test")

    async def test_anthropic_context_length_exceeded(self):
        """AnthropicAdapter handles context length exceeded (400 error)."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)

        from anthropic import BadRequestError

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.headers = {}
        error = BadRequestError(
            message="prompt is too long: max context length exceeded",
            response=mock_response,
            body={"error": {"message": "prompt is too long"}},
        )

        adapter._client = MagicMock()
        adapter._client.messages.create = AsyncMock(side_effect=error)

        with pytest.raises(BadRequestError, match="too long"):
            await adapter.generate("Test")

    async def test_anthropic_timeout_error(self):
        """AnthropicAdapter handles timeout errors."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)

        from anthropic import APITimeoutError

        error = APITimeoutError(request=MagicMock())

        adapter._client = MagicMock()
        adapter._client.messages.create = AsyncMock(side_effect=error)

        with pytest.raises(APITimeoutError):
            await adapter.generate("Test")

    async def test_anthropic_parse_update_malformed_json(self):
        """AnthropicAdapter.parse_update handles malformed JSON gracefully."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)

        update = adapter.parse_update("not valid json {{{")
        assert isinstance(update, HiveUpdate)
        assert update.source_model == "claude"

    async def test_anthropic_generate_empty_response(self):
        """AnthropicAdapter handles empty content from API."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
        )
        adapter = AnthropicAdapter(config)

        mock_response = MagicMock()
        mock_response.content = []
        mock_response.stop_reason = "end_turn"
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=0)

        adapter._client = MagicMock()
        adapter._client.messages.create = AsyncMock(return_value=mock_response)

        result = await adapter.generate("Test")
        assert result == ""


# ============================================================
# Factory Routing Tests
# ============================================================


class TestFactoryRouting:
    """Tests for adapter factory routing to new providers."""

    def test_factory_creates_openai_adapter(self):
        """create_adapter routes to OpenAIAdapter for openai provider."""
        config = ModelConfig(
            name="openai",
            model_id="gpt-4-turbo",
            api_key="sk-test",
            extra_params={"provider": "openai"},
        )
        adapter = create_adapter(config)
        # Amendment 9: assert specific values, not just isinstance
        assert isinstance(adapter, OpenAIAdapter)
        assert adapter.config.model_id == "gpt-4-turbo"
        assert adapter._api_key == "sk-test"

    def test_factory_creates_anthropic_adapter(self):
        """create_adapter routes to AnthropicAdapter for anthropic provider."""
        config = ModelConfig(
            name="claude",
            model_id="claude-3-sonnet-20240229",
            api_key="sk-ant-test",
            extra_params={"provider": "anthropic"},
        )
        adapter = create_adapter(config)
        # Amendment 9: assert specific values, not just isinstance
        assert isinstance(adapter, AnthropicAdapter)
        assert adapter.config.model_id == "claude-3-sonnet-20240229"
        assert adapter._api_key == "sk-ant-test"

    def test_factory_still_routes_groq(self):
        """create_adapter still routes groq provider correctly after changes."""
        config = ModelConfig(
            name="groq",
            model_id="llama3-70b",
            api_key="gsk-test",
            extra_params={"provider": "groq"},
        )
        from vecna.adapters.base import GroqAdapter

        adapter = create_adapter(config)
        assert isinstance(adapter, GroqAdapter)
        assert adapter.config.model_id == "llama3-70b"


# ============================================================
# Provider Enum Tests
# ============================================================


class TestProviderEnum:
    """Tests for Provider enum updates."""

    def test_openai_in_provider_enum(self):
        """Provider enum includes OPENAI with correct value."""
        from vecna.config.schema import Provider

        assert hasattr(Provider, "OPENAI")
        assert Provider.OPENAI.value == "openai"

    def test_anthropic_in_provider_enum(self):
        """Provider enum includes ANTHROPIC with correct value."""
        from vecna.config.schema import Provider

        assert hasattr(Provider, "ANTHROPIC")
        assert Provider.ANTHROPIC.value == "anthropic"

    def test_existing_providers_unchanged(self):
        """Existing Provider enum values are not broken."""
        from vecna.config.schema import Provider

        assert Provider.COPILOT.value == "copilot"
        assert Provider.OLLAMA.value == "ollama"
        assert Provider.GROQ.value == "groq"
        assert Provider.TRANSFORMERS.value == "transformers"


# ============================================================
# Config Factory Tests
# ============================================================


class TestConfigFactory:
    """Tests for config factory routing to new providers."""

    def test_config_factory_creates_openai_adapter(self):
        """create_adapter_from_entry routes OPENAI to OpenAIAdapter."""
        from vecna.config.schema import Provider, ModelEntry
        from vecna.config.factory import create_adapter_from_entry

        entry = ModelEntry(
            name="openai-gpt4",
            provider=Provider.OPENAI,
            model_id="gpt-4-turbo",
            api_key_env="OPENAI_API_KEY",
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}):
            adapter = create_adapter_from_entry(entry)
            assert isinstance(adapter, OpenAIAdapter)
            assert adapter.config.model_id == "gpt-4-turbo"
            assert adapter._api_key == "sk-test"

    def test_config_factory_creates_anthropic_adapter(self):
        """create_adapter_from_entry routes ANTHROPIC to AnthropicAdapter."""
        from vecna.config.schema import Provider, ModelEntry
        from vecna.config.factory import create_adapter_from_entry

        entry = ModelEntry(
            name="claude-sonnet",
            provider=Provider.ANTHROPIC,
            model_id="claude-3-sonnet-20240229",
            api_key_env="ANTHROPIC_API_KEY",
        )

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-ant-test"}):
            adapter = create_adapter_from_entry(entry)
            assert isinstance(adapter, AnthropicAdapter)
            assert adapter.config.model_id == "claude-3-sonnet-20240229"
            assert adapter._api_key == "sk-ant-test"

    def test_config_factory_skips_missing_api_key(self):
        """create_adapter_from_entry returns None if API key env var not set."""
        from vecna.config.schema import Provider, ModelEntry
        from vecna.config.factory import create_adapter_from_entry

        entry = ModelEntry(
            name="openai-gpt4",
            provider=Provider.OPENAI,
            model_id="gpt-4-turbo",
            api_key_env="OPENAI_API_KEY",
        )

        with patch.dict("os.environ", {}, clear=True):
            adapter = create_adapter_from_entry(entry)
            assert adapter is None
