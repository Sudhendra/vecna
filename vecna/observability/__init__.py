"""
Observability module for Vecna.

Provides tracing, token usage tracking, and cost monitoring via Langfuse.
"""

from vecna.observability.langfuse import (
    get_langfuse,
    create_trace,
    get_current_trace,
    set_current_trace,
    clear_current_trace,
    end_trace,
    create_generation,
    create_span,
    end_span,
    TracedOperation,
    is_tracing_enabled,
    should_log_prompts,
    should_trace_pipeline,
    flush,
    shutdown,
)
from vecna.observability.tokens import (
    estimate_tokens,
    estimate_message_tokens,
    get_usage_from_response,
    estimate_usage,
    get_or_estimate_usage,
)

__all__ = [
    # Langfuse client
    "get_langfuse",
    "create_trace",
    "get_current_trace",
    "set_current_trace",
    "clear_current_trace",
    "end_trace",
    "create_generation",
    "create_span",
    "end_span",
    "TracedOperation",
    "is_tracing_enabled",
    "should_log_prompts",
    "should_trace_pipeline",
    "flush",
    "shutdown",
    # Token utilities
    "estimate_tokens",
    "estimate_message_tokens",
    "get_usage_from_response",
    "estimate_usage",
    "get_or_estimate_usage",
]
