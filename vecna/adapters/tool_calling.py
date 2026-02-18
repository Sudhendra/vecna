"""
Native tool calling support for model adapters.

Replaces the fragile <HIVE_UPDATE> YAML parsing with
proper function calling / tool use that models natively support.

This module defines two shared functions (Amendment 5):
- build_hive_update_tool_schema(): the OpenAI-style function schema
- parse_tool_call_update(): converts tool-call args to HiveUpdate

All adapters that support tool calling (OpenAI, Anthropic, etc.)
MUST import and use these functions — no duplicate parse_update() methods.
"""

import logging
from typing import Any, Dict, List

from vecna.core.types import HiveUpdate

logger = logging.getLogger("vecna.adapters.tool_calling")


def build_hive_update_tool_schema() -> Dict[str, Any]:
    """
    Build the tool/function schema for hive state updates.

    This schema is passed to models that support native tool calling
    (OpenAI, Anthropic, etc.) so they can produce structured updates
    without relying on the custom <HIVE_UPDATE> YAML format.

    Returns an OpenAI-compatible function-calling tool definition.
    """
    return {
        "type": "function",
        "function": {
            "name": "hive_update",
            "description": (
                "Update the hive mind's shared mental state with new knowledge, "
                "beliefs, hypotheses, and observations from this interaction."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "new_facts": {
                        "type": "array",
                        "description": "New verified facts learned",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {
                                    "type": "string",
                                    "description": "The fact statement",
                                },
                                "confidence": {
                                    "type": "number",
                                    "description": "0.0 to 1.0",
                                },
                                "evidence": {
                                    "type": "string",
                                    "description": "Why this is true",
                                },
                                "domain": {
                                    "type": "string",
                                    "description": "Knowledge domain",
                                },
                            },
                            "required": ["content"],
                        },
                    },
                    "belief_changes": {
                        "type": "array",
                        "description": "Updated or new beliefs",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "confidence": {"type": "number"},
                                "reasoning": {"type": "string"},
                            },
                            "required": ["content"],
                        },
                    },
                    "hypotheses": {
                        "type": "array",
                        "description": "Tentative ideas to explore",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "confidence": {"type": "number"},
                                "notes": {"type": "string"},
                            },
                            "required": ["content"],
                        },
                    },
                    "open_questions": {
                        "type": "array",
                        "description": "Unresolved questions",
                        "items": {
                            "type": "object",
                            "properties": {
                                "question": {"type": "string"},
                                "priority": {"type": "string"},
                            },
                            "required": ["question"],
                        },
                    },
                    "contradictions": {
                        "type": "array",
                        "description": "Detected conflicts",
                        "items": {
                            "type": "object",
                            "properties": {
                                "item_a": {"type": "string"},
                                "item_b": {"type": "string"},
                            },
                            "required": ["item_a", "item_b"],
                        },
                    },
                    "overall_confidence": {
                        "type": "number",
                        "description": ("Overall confidence in this update (0.0-1.0)"),
                    },
                    "user_preferences_observed": {
                        "type": "array",
                        "description": ("Observed user preferences from this interaction"),
                        "items": {
                            "type": "object",
                            "properties": {
                                "key": {"type": "string"},
                                "value": {"type": "string"},
                                "confidence": {"type": "number"},
                            },
                            "required": ["key", "value"],
                        },
                    },
                },
            },
        },
    }


def _coerce_list(value: Any) -> List[Dict[str, Any]]:
    """Safely coerce a value to a list, returning [] for None or non-list."""
    if value is None:
        return []
    if not isinstance(value, list):
        logger.warning(
            "Expected list for tool call field, got %s; using empty list",
            type(value).__name__,
        )
        return []
    return value


def _clamp_confidence(value: Any) -> float:
    """
    Convert and clamp a confidence value to [0.0, 1.0].

    Returns None if the value cannot be converted to a float,
    signalling the caller to keep the default.
    """
    try:
        numeric = float(value)
    except (ValueError, TypeError):
        return None
    return max(0.0, min(1.0, numeric))


def parse_tool_call_update(
    args: Dict[str, Any],
    source_model: str,
) -> HiveUpdate:
    """
    Parse a tool call response dict into a HiveUpdate.

    This is the canonical parser for all adapters (Amendment 5).
    Uses source_model field name per Amendment 6.
    Handles malformed input gracefully per Amendment 8.

    Args:
        args: The tool call arguments dict from the model response.
        source_model: Which adapter/model produced this update.

    Returns:
        A populated HiveUpdate instance.
    """
    update = HiveUpdate(source_model=source_model)

    update.new_facts = _coerce_list(args.get("new_facts"))
    update.belief_changes = _coerce_list(args.get("belief_changes"))
    update.new_hypotheses = _coerce_list(args.get("hypotheses"))
    update.open_questions = _coerce_list(args.get("open_questions"))
    update.contradictions_found = _coerce_list(args.get("contradictions"))
    update.user_preferences_observed = _coerce_list(args.get("user_preferences_observed"))

    confidence = args.get("overall_confidence")
    if confidence is not None:
        clamped = _clamp_confidence(confidence)
        if clamped is not None:
            update.confidence = clamped
        else:
            logger.warning(
                "Invalid confidence value %r from %s; keeping default",
                confidence,
                source_model,
            )

    return update
