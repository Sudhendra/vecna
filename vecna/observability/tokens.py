"""
Token estimation utilities for Vecna.

Provides token counting/estimation for cost tracking with Langfuse.
Uses tiktoken when available, falls back to character-based estimation.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("vecna.observability.tokens")

# Lazy-loaded encoder
_encoder = None


def _get_encoder():
    """Get or create tiktoken encoder (lazy init)."""
    global _encoder
    if _encoder is not None:
        return _encoder

    try:
        import tiktoken

        # cl100k_base works for GPT-4, GPT-3.5, text-embedding-ada-002
        # It's a reasonable approximation for most modern models
        _encoder = tiktoken.get_encoding("cl100k_base")
        logger.debug("Using tiktoken cl100k_base encoder")
        return _encoder
    except ImportError:
        logger.debug("tiktoken not available, will use character estimation")
        return None
    except Exception as e:
        logger.debug(f"tiktoken initialization failed: {e}")
        return None


def estimate_tokens(text: str, model: Optional[str] = None) -> int:
    """
    Estimate token count for text.

    Uses tiktoken if available, falls back to character estimation.

    Args:
        text: Text to count tokens for
        model: Model identifier (unused currently, for future model-specific encoders)

    Returns:
        Estimated token count
    """
    if not text:
        return 0

    encoder = _get_encoder()

    if encoder is not None:
        try:
            return len(encoder.encode(text))
        except Exception as e:
            logger.debug(f"tiktoken encoding failed: {e}")

    # Fallback: ~4 characters per token (rough estimate for English text)
    # This is based on OpenAI's guidance that 1 token ≈ 4 characters
    return len(text) // 4


def estimate_message_tokens(messages: list, model: Optional[str] = None) -> int:
    """
    Estimate token count for a list of chat messages.

    Accounts for message formatting overhead (~4 tokens per message).

    Args:
        messages: List of message dicts with 'role' and 'content'
        model: Model identifier

    Returns:
        Estimated token count
    """
    if not messages:
        return 0

    total = 0
    for msg in messages:
        # ~4 tokens overhead per message for formatting
        total += 4
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if content:
                total += estimate_tokens(str(content), model)
            role = msg.get("role", "")
            if role:
                total += estimate_tokens(role, model)
        else:
            total += estimate_tokens(str(msg), model)

    # ~2 tokens for priming the assistant response
    total += 2

    return total


def get_usage_from_response(response: Any, provider: str) -> Optional[Dict[str, int]]:
    """
    Extract token usage from provider response.

    Args:
        response: Provider API response (dict or object)
        provider: Provider name ("openai", "copilot", "groq", "ollama", etc.)

    Returns:
        Dict with prompt_tokens, completion_tokens, total_tokens or None if not available
    """
    if response is None:
        return None

    # Normalize to dict if needed
    if hasattr(response, "model_dump"):
        # Pydantic model
        response_dict = response.model_dump()
    elif hasattr(response, "__dict__"):
        response_dict = response.__dict__
    elif isinstance(response, dict):
        response_dict = response
    else:
        return None

    # OpenAI / Copilot / Groq format (standard OpenAI response)
    if provider in ("openai", "copilot", "groq", "azure"):
        usage = response_dict.get("usage")
        if usage:
            if isinstance(usage, dict):
                usage_dict = usage
            elif hasattr(usage, "model_dump"):
                usage_dict = usage.model_dump()
            elif hasattr(usage, "__dict__"):
                usage_dict = usage.__dict__
            else:
                return None

            prompt_tokens = usage_dict.get("prompt_tokens", 0)
            completion_tokens = usage_dict.get("completion_tokens", 0)
            total_tokens = usage_dict.get("total_tokens", 0)

            if total_tokens == 0 and (prompt_tokens or completion_tokens):
                total_tokens = prompt_tokens + completion_tokens

            if prompt_tokens or completion_tokens or total_tokens:
                return {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                }

    # Ollama format
    if provider == "ollama":
        prompt_tokens = response_dict.get("prompt_eval_count", 0)
        completion_tokens = response_dict.get("eval_count", 0)
        if prompt_tokens or completion_tokens:
            return {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            }

    # Anthropic format
    if provider == "anthropic":
        usage = response_dict.get("usage")
        if usage:
            if isinstance(usage, dict):
                usage_dict = usage
            else:
                usage_dict = getattr(usage, "__dict__", {})

            input_tokens = usage_dict.get("input_tokens", 0)
            output_tokens = usage_dict.get("output_tokens", 0)

            if input_tokens or output_tokens:
                return {
                    "prompt_tokens": input_tokens,
                    "completion_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }

    return None


def estimate_usage(
    prompt: str,
    response: str,
    model: Optional[str] = None,
) -> Dict[str, int]:
    """
    Estimate token usage when provider doesn't return it.

    Args:
        prompt: Full prompt text
        response: Response text
        model: Model identifier (for future model-specific estimation)

    Returns:
        Dict with prompt_tokens, completion_tokens, total_tokens
    """
    prompt_tokens = estimate_tokens(prompt, model) if prompt else 0
    completion_tokens = estimate_tokens(response, model) if response else 0

    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def get_or_estimate_usage(
    response: Any,
    provider: str,
    prompt: Optional[str] = None,
    response_text: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, int]:
    """
    Get usage from response if available, otherwise estimate.

    This is the main entry point for hybrid token accounting.

    Args:
        response: Provider API response
        provider: Provider name
        prompt: Prompt text (for estimation fallback)
        response_text: Response text (for estimation fallback)
        model: Model identifier

    Returns:
        Dict with prompt_tokens, completion_tokens, total_tokens
    """
    # Try to get actual usage from response
    usage = get_usage_from_response(response, provider)
    if usage:
        return usage

    # Fall back to estimation
    if prompt is not None or response_text is not None:
        return estimate_usage(prompt or "", response_text or "", model)

    # No data available
    return {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
