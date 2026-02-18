"""Anthropic native adapter with tool use support.

Uses the anthropic Python SDK for direct API access with native
tool use for structured hive state updates. Shared schema and
parsing via tool_calling.py (Amendment 5).
"""

import json
import logging
import os
from typing import Any, AsyncIterator, Dict, List

from vecna.adapters.base import BaseAdapter, ModelConfig
from vecna.core.types import HiveUpdate

logger = logging.getLogger("vecna.anthropic_adapter")


def _build_hive_update_tool_anthropic() -> Dict[str, Any]:
    """Build hive_update tool schema in Anthropic tool use format.

    Amendment 5: Uses shared build_hive_update_tool_schema() — no
    duplicate schema definitions. Wraps the shared schema in
    Anthropic's expected format (name, description, input_schema).
    """
    from vecna.adapters.tool_calling import build_hive_update_tool_schema

    schema = build_hive_update_tool_schema()
    func = schema["function"]
    return {
        "name": func["name"],
        "description": func["description"],
        "input_schema": func["parameters"],
    }


class AnthropicAdapter(BaseAdapter):
    """Native Anthropic adapter using the anthropic SDK.

    Supports tool use via the hive_update tool schema and
    streaming responses. Uses the anthropic Python SDK directly.

    Requires either:
    - api_key in ModelConfig, or
    - ANTHROPIC_API_KEY environment variable
    """

    def __init__(self, config: ModelConfig) -> None:
        super().__init__(config)
        self._api_key = config.api_key or os.getenv("ANTHROPIC_API_KEY", "")
        if not self._api_key:
            raise ValueError(
                "Anthropic API key required. Set api_key in config "
                "or ANTHROPIC_API_KEY environment variable."
            )
        self._client: Any = None
        self._last_response_data: Any = None
        self._init_client()

    def _init_client(self) -> None:
        """Initialize the Anthropic async client."""
        try:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(api_key=self._api_key)
            logger.info(
                "Anthropic client initialized for model %s",
                self.config.model_id,
            )
        except ImportError:
            logger.error("anthropic package not installed. Install with: pip install anthropic")
            raise

    def _get_provider_name(self) -> str:
        """Return provider name for tracing and token extraction."""
        return "anthropic"

    async def generate(self, prompt: str) -> str:
        """Generate a response using Anthropic messages API.

        If the model returns a tool_use block for hive_update,
        the tool input is returned as a JSON string. Otherwise
        the text content is returned directly.

        Args:
            prompt: The input prompt.

        Returns:
            Response text or JSON tool input.

        Raises:
            anthropic.APIError: On API errors (rate limit, auth, etc.)
        """
        import anthropic

        system_msg = self.get_system_message() or ""
        tools = [_build_hive_update_tool_anthropic()]

        try:
            response = await self._client.messages.create(
                model=self.config.model_id,
                max_tokens=self.config.max_tokens or 1024,
                system=system_msg,
                messages=[{"role": "user", "content": prompt}],
                tools=tools,
            )
        except anthropic.AuthenticationError:
            logger.error("Anthropic authentication failed — check API key")
            raise
        except anthropic.RateLimitError:
            logger.error(
                "Anthropic rate limit exceeded for model %s",
                self.config.model_id,
            )
            raise
        except anthropic.BadRequestError:
            logger.error(
                "Anthropic bad request for model %s",
                self.config.model_id,
            )
            raise
        except anthropic.APITimeoutError:
            logger.error(
                "Anthropic request timed out for model %s",
                self.config.model_id,
            )
            raise
        except anthropic.APIError as e:
            logger.error("Anthropic API call failed: %s", e)
            raise

        self._last_response_data = response

        # Check for tool_use blocks — return hive_update input as JSON
        for block in response.content:
            if block.type == "tool_use" and block.name == "hive_update":
                return json.dumps(block.input)

        # Concatenate text blocks
        text_parts: List[str] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
        return "".join(text_parts)

    async def generate_stream(self, prompt: str) -> AsyncIterator[str]:
        """Stream response chunks from Anthropic.

        Uses Anthropic's streaming messages API. Yields text
        delta chunks as they arrive.

        Args:
            prompt: The input prompt.

        Yields:
            Text chunks as they arrive.

        Raises:
            anthropic.APIError: On API errors.
        """
        import anthropic

        system_msg = self.get_system_message() or ""

        try:
            async with self._client.messages.stream(
                model=self.config.model_id,
                max_tokens=self.config.max_tokens or 1024,
                system=system_msg,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for event in stream:
                    if event.type == "content_block_delta":
                        if event.delta.type == "text_delta":
                            yield event.delta.text
        except anthropic.APIError as e:
            logger.error("Anthropic streaming failed: %s", e)
            raise

    def parse_update(self, output: str) -> HiveUpdate:
        """Parse tool use JSON into HiveUpdate.

        Amendment 5: Uses shared parse_tool_call_update() from
        tool_calling.py instead of duplicating parsing logic.

        Falls back to BaseAdapter YAML parsing if JSON fails
        (e.g., when model returns plain text with <HIVE_UPDATE>).
        """
        try:
            args = json.loads(output)
            if isinstance(args, dict):
                from vecna.adapters.tool_calling import parse_tool_call_update

                return parse_tool_call_update(args, source_model=self.config.name)
        except (json.JSONDecodeError, ValueError):
            logger.debug("Anthropic output not valid JSON, falling back to YAML parse")

        # Fall back to base YAML parsing for non-JSON output
        return super().parse_update(output)
