"""OpenAI native adapter with function calling support.

Uses the openai Python SDK for direct API access with native
tool calling for structured hive state updates. Shared schema
and parsing via tool_calling.py (Amendment 5).
"""

import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List

from vecna.adapters.base import BaseAdapter, ModelConfig
from vecna.adapters.tool_calling import parse_tool_call_update

logger = logging.getLogger("vecna.openai_adapter")


def _build_hive_update_tool_openai() -> Dict[str, Any]:
    """Build hive_update tool schema in OpenAI function calling format.

    Amendment 5: Uses shared build_hive_update_tool_schema() — no
    duplicate schema definitions. The shared schema already returns
    the OpenAI-compatible format with type/function wrapper.
    """
    from vecna.adapters.tool_calling import build_hive_update_tool_schema

    return build_hive_update_tool_schema()


class OpenAIAdapter(BaseAdapter):
    """Native OpenAI adapter using the openai SDK.

    Supports function calling via the hive_update tool schema
    and streaming responses. Uses the openai Python SDK directly.

    Requires either:
    - api_key in ModelConfig, or
    - OPENAI_API_KEY environment variable
    """

    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        self._api_key = config.api_key or os.getenv("OPENAI_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "OpenAI API key required. Set api_key in config "
                "or OPENAI_API_KEY environment variable."
            )
        self._client: Any = None
        self._last_response_data: Any = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize the OpenAI async client."""
        try:
            from openai import AsyncOpenAI

            base_url = self.config.base_url or None
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=base_url,
            )
            logger.info(
                "OpenAI client initialized for model %s",
                self.config.model_id,
            )
        except ImportError:
            logger.error("openai package not installed. Install with: pip install openai")
            raise

    def _get_provider_name(self) -> str:
        """Return provider name for tracing and token extraction."""
        return "openai"

    def _build_messages(self, prompt: str) -> List[Dict[str, str]]:
        """Build chat messages from prompt with system message."""
        system_msg = self.get_system_message()
        messages: List[Dict[str, str]] = []
        if system_msg:
            messages.append({"role": "system", "content": system_msg})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def generate(self, prompt: str) -> str:
        """Generate a response using OpenAI chat completions.

        If the model returns a tool call for hive_update, the tool
        call arguments are returned as a JSON string. Otherwise
        the text content is returned directly.

        Args:
            prompt: The input prompt.

        Returns:
            Response text or JSON tool call arguments.

        Raises:
            openai.APIError: On API errors (rate limit, auth, etc.)
        """
        import openai

        messages = self._build_messages(prompt)
        tools = [_build_hive_update_tool_openai()]

        try:
            response = await self._client.chat.completions.create(
                model=self.config.model_id,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
            )
        except openai.RateLimitError:
            logger.error(
                "OpenAI rate limit exceeded for model %s",
                self.config.model_id,
            )
            raise
        except openai.APITimeoutError:
            logger.error(
                "OpenAI request timed out for model %s",
                self.config.model_id,
            )
            raise
        except openai.AuthenticationError:
            logger.error("OpenAI authentication failed — check API key")
            raise
        except openai.BadRequestError:
            logger.error(
                "OpenAI bad request for model %s",
                self.config.model_id,
            )
            raise
        except openai.APIError as e:
            logger.error("OpenAI API call failed: %s", e)
            raise

        self._last_response_data = response

        choice = response.choices[0]

        # Check for tool calls — return hive_update args as JSON
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                if tc.function.name == "hive_update":
                    try:
                        args = json.loads(tc.function.arguments)
                        if isinstance(args, dict):
                            parse_tool_call_update(args, source_model=self.config.name)
                    except (json.JSONDecodeError, TypeError, ValueError):
                        logger.debug("OpenAI hive_update arguments were not valid JSON")
                    return tc.function.arguments
            # Non-hive_update tool calls: return text content
            return choice.message.content or ""

        return choice.message.content or ""

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        """Stream response chunks from OpenAI.

        Yields text chunks as they arrive. Does not include tool
        calling in streaming mode — use generate() for structured
        responses.

        Args:
            prompt: The input prompt.

        Yields:
            Text chunks as they arrive.

        Raises:
            openai.APIError: On API errors.
        """
        import openai

        messages = self._build_messages(prompt)

        try:
            stream = await self._client.chat.completions.create(
                model=self.config.model_id,
                messages=messages,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except openai.APIError as e:
            logger.error("OpenAI streaming failed: %s", e)
            raise
