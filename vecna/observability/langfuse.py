"""
Langfuse tracing integration for Vecna (v3 API).

Provides:
- Trace/span creation for LLM calls
- Token usage tracking
- Fail-open behavior (no crash if Langfuse down)
- Privacy controls (redaction)

Environment Variables:
    LANGFUSE_PUBLIC_KEY: Langfuse project public key
    LANGFUSE_SECRET_KEY: Langfuse project secret key
    LANGFUSE_BASE_URL: Langfuse server URL (default: https://cloud.langfuse.com)
    VECNA_LANGFUSE_ENABLED: Enable Langfuse tracing (default: false)
    VECNA_LANGFUSE_LOG_PROMPTS: Log full prompt/response text (default: true)
    VECNA_LANGFUSE_TRACE_PIPELINE: Trace memory/consensus/code spans (default: true)
"""

import hashlib
import logging
import os
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Dict, Generator, Optional, Union

logger = logging.getLogger("vecna.observability.langfuse")

# Global client instance (lazy init)
_client = None

# Context variable to track if we're in a traced context
_trace_active: ContextVar[bool] = ContextVar("trace_active", default=False)


def is_tracing_enabled() -> bool:
    """Check if Langfuse tracing is enabled."""
    return os.getenv("VECNA_LANGFUSE_ENABLED", "").lower() == "true"


def should_log_prompts() -> bool:
    """Check if full prompt/response logging is enabled."""
    return os.getenv("VECNA_LANGFUSE_LOG_PROMPTS", "true").lower() == "true"


def should_trace_pipeline() -> bool:
    """Check if pipeline spans (memory, consensus, code) are enabled."""
    return os.getenv("VECNA_LANGFUSE_TRACE_PIPELINE", "true").lower() == "true"


def get_langfuse():
    """
    Get or create Langfuse client (lazy init).

    Returns None if:
    - Tracing is disabled
    - Langfuse keys are not configured
    - Langfuse import/initialization fails
    """
    global _client

    if _client is not None:
        return _client

    if not is_tracing_enabled():
        return None

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")

    if not public_key or not secret_key:
        logger.warning("Langfuse keys not configured, tracing disabled")
        return None

    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            host=os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
        )
        logger.info(
            f"Langfuse client initialized (host: {os.getenv('LANGFUSE_BASE_URL', 'cloud')})"
        )
        return _client
    except ImportError:
        logger.warning("langfuse package not installed, tracing disabled")
        return None
    except Exception as e:
        logger.warning(f"Failed to initialize Langfuse: {e}")
        return None


def _redact(content: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    Return redacted metadata instead of full content.

    Used when VECNA_LANGFUSE_LOG_PROMPTS=false.
    """
    if not content:
        return None
    return {
        "redacted": True,
        "length": len(content),
        "hash": hashlib.sha256(content.encode()).hexdigest()[:16],
    }


def _maybe_redact(content: Optional[str]) -> Optional[Union[str, Dict[str, Any]]]:
    """Return content or redacted version based on logging settings."""
    if should_log_prompts():
        return content
    return _redact(content)


def is_trace_active() -> bool:
    """Check if we're currently in a traced context."""
    return _trace_active.get()


def get_current_trace():
    """Get the current trace context (for compatibility)."""
    if is_trace_active():
        return True  # Return truthy value to indicate trace is active
    return None


def set_current_trace(trace):
    """Set trace as active (for compatibility)."""
    _trace_active.set(trace is not None)


def clear_current_trace():
    """Clear the current trace (for compatibility)."""
    _trace_active.set(False)


@contextmanager
def trace_request(
    name: str,
    input: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Generator[Any, None, None]:
    """
    Context manager to trace a full request (creates root span).

    Usage:
        with trace_request("hive.think", input=task) as trace_ctx:
            # All nested spans/generations will be children
            response = do_work()
            trace_ctx.update(output=response)

    Args:
        name: Trace/span name
        input: Input text (will be redacted if logging disabled)
        metadata: Additional metadata dict
        tags: Optional list of tags
        session_id: Session identifier
        user_id: User identifier
    """
    client = get_langfuse()
    if not client:
        # Yield a no-op context if Langfuse is not available
        yield _NoOpTraceContext()
        return

    try:
        # Use start_as_current_span to create a root span (trace)
        with client.start_as_current_span(
            name=name,
            input=_maybe_redact(input),
            metadata={
                **(metadata or {}),
                "tags": tags,
                "session_id": session_id,
                "user_id": user_id,
            },
        ) as span:
            _trace_active.set(True)
            yield _TraceContext(span, client)
    except Exception as e:
        logger.warning(f"Failed to create trace: {e}")
        yield _NoOpTraceContext()
    finally:
        _trace_active.set(False)


class _NoOpTraceContext:
    """No-op trace context when Langfuse is not available."""

    def update(self, **kwargs):
        pass

    def set_output(self, output: str):
        pass

    def set_metadata(self, metadata: Dict[str, Any]):
        pass

    def set_level(self, level: str):
        pass

    def set_status_message(self, message: str):
        pass


class _TraceContext:
    """Wrapper around Langfuse span for trace context."""

    def __init__(self, span, client):
        self.span = span
        self.client = client
        self._metadata = {}

    def update(
        self,
        output: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        level: Optional[str] = None,
        status_message: Optional[str] = None,
    ):
        """Update the trace with output and metadata."""
        try:
            if output is not None:
                self.span.update(output=_maybe_redact(output))
            if metadata is not None:
                self.span.update(metadata=metadata)
            if level is not None:
                self.span.update(level=level)
            if status_message is not None:
                self.span.update(status_message=status_message)
        except Exception as e:
            logger.warning(f"Failed to update trace: {e}")

    def set_output(self, output: str):
        self.update(output=output)

    def set_metadata(self, metadata: Dict[str, Any]):
        self._metadata.update(metadata)
        self.update(metadata=self._metadata)

    def set_level(self, level: str):
        self.update(level=level)

    def set_status_message(self, message: str):
        self.update(status_message=message)


@contextmanager
def trace_generation(
    name: str,
    model: str,
    input: Optional[str] = None,
    model_parameters: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Context manager to trace an LLM generation.

    Usage:
        with trace_generation("llm.gpt-4", model="gpt-4", input=prompt) as gen:
            response = call_llm(prompt)
            gen.set_output(response)
            gen.set_usage(prompt_tokens=100, completion_tokens=50)

    Args:
        name: Generation name
        model: Model identifier
        input: Prompt text
        model_parameters: Model config (temperature, max_tokens, etc.)
        metadata: Additional metadata
    """
    client = get_langfuse()
    if not client or not is_trace_active():
        yield _NoOpGenerationContext()
        return

    try:
        with client.start_as_current_generation(
            name=name,
            model=model,
            input=_maybe_redact(input),
            model_parameters=model_parameters,
            metadata=metadata,
        ) as generation:
            yield _GenerationContext(generation)
    except Exception as e:
        logger.warning(f"Failed to create generation: {e}")
        yield _NoOpGenerationContext()


class _NoOpGenerationContext:
    """No-op generation context when Langfuse is not available."""

    def set_output(self, output: str):
        pass

    def set_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0, total_tokens: int = 0):
        pass

    def set_metadata(self, metadata: Dict[str, Any]):
        pass

    def update(self, **kwargs):
        pass


class _GenerationContext:
    """Wrapper around Langfuse generation span."""

    def __init__(self, generation):
        self.generation = generation
        self._metadata = {}

    def set_output(self, output: str):
        try:
            self.generation.update(output=_maybe_redact(output))
        except Exception as e:
            logger.warning(f"Failed to set generation output: {e}")

    def set_usage(self, prompt_tokens: int = 0, completion_tokens: int = 0, total_tokens: int = 0):
        try:
            if total_tokens == 0:
                total_tokens = prompt_tokens + completion_tokens
            self.generation.update(
                usage_details={
                    "input": prompt_tokens,
                    "output": completion_tokens,
                    "total": total_tokens,
                }
            )
        except Exception as e:
            logger.warning(f"Failed to set generation usage: {e}")

    def set_metadata(self, metadata: Dict[str, Any]):
        try:
            self._metadata.update(metadata)
            self.generation.update(metadata=self._metadata)
        except Exception as e:
            logger.warning(f"Failed to set generation metadata: {e}")

    def update(self, **kwargs):
        try:
            self.generation.update(**kwargs)
        except Exception as e:
            logger.warning(f"Failed to update generation: {e}")


@contextmanager
def trace_span(
    name: str,
    input: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Generator[Any, None, None]:
    """
    Context manager to trace a non-LLM operation (span).

    Used for memory retrieval, consensus, code execution, etc.

    Usage:
        with trace_span("memory.retrieval") as span:
            result = retrieve_memory(query)
            span.set_metadata({"items": len(result)})

    Args:
        name: Span name
        input: Input description
        metadata: Initial metadata
    """
    client = get_langfuse()
    if not client or not is_trace_active() or not should_trace_pipeline():
        yield _NoOpSpanContext()
        return

    start_time = time.time()
    try:
        with client.start_as_current_span(
            name=name,
            input=_maybe_redact(input),
            metadata=metadata,
        ) as span:
            ctx = _SpanContext(span, start_time)
            yield ctx
            # Auto-add duration on exit
            ctx._finalize()
    except Exception as e:
        logger.warning(f"Failed to create span: {e}")
        yield _NoOpSpanContext()


class _NoOpSpanContext:
    """No-op span context when Langfuse is not available."""

    def set_output(self, output: str):
        pass

    def set_metadata(self, metadata: Dict[str, Any]):
        pass

    def set_level(self, level: str):
        pass

    def set_status_message(self, message: str):
        pass


class _SpanContext:
    """Wrapper around Langfuse span."""

    def __init__(self, span, start_time: float):
        self.span = span
        self.start_time = start_time
        self._metadata = {}
        self._output = None
        self._level = None
        self._status_message = None

    def set_output(self, output: str):
        self._output = output

    def set_metadata(self, metadata: Dict[str, Any]):
        self._metadata.update(metadata)

    def set_level(self, level: str):
        self._level = level

    def set_status_message(self, message: str):
        self._status_message = message

    def _finalize(self):
        """Finalize span with accumulated data."""
        try:
            duration_ms = (time.time() - self.start_time) * 1000
            final_metadata = {**self._metadata, "duration_ms": round(duration_ms, 2)}

            update_kwargs = {"metadata": final_metadata}
            if self._output is not None:
                update_kwargs["output"] = _maybe_redact(self._output)
            if self._level is not None:
                update_kwargs["level"] = self._level
            if self._status_message is not None:
                update_kwargs["status_message"] = self._status_message

            self.span.update(**update_kwargs)
        except Exception as e:
            logger.warning(f"Failed to finalize span: {e}")


# Legacy compatibility aliases
class TracedOperation:
    """
    Legacy context manager for traced operations.
    Use trace_span() instead for new code.
    """

    def __init__(
        self,
        trace,  # Ignored in v3 API
        name: str,
        input: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.name = name
        self.input = input
        self.initial_metadata = metadata or {}
        self._ctx = None
        self._span_cm = None

    def __enter__(self):
        self._span_cm = trace_span(self.name, self.input, self.initial_metadata)
        self._ctx = self._span_cm.__enter__()
        return self._ctx

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._ctx.set_level("ERROR")
            self._ctx.set_status_message(str(exc_val))
        return self._span_cm.__exit__(exc_type, exc_val, exc_tb)


# Legacy compatibility functions
def create_trace(
    name: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    input: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[list] = None,
):
    """Legacy function - returns a context manager handle. Use trace_request() instead."""
    # Return a "trace handle" that the old code expects
    return _LegacyTraceHandle(name, session_id, user_id, input, metadata, tags)


class _LegacyTraceHandle:
    """Handle for legacy trace API compatibility."""

    def __init__(self, name, session_id, user_id, input, metadata, tags):
        self.name = name
        self.session_id = session_id
        self.user_id = user_id
        self.input = input
        self.metadata = metadata
        self.tags = tags
        self._active = False
        self._span_cm = None
        self._ctx = None

    def __bool__(self):
        return True  # Always truthy to indicate trace was "created"

    def start(self):
        """Start the trace (enter context)."""
        client = get_langfuse()
        if not client:
            return
        try:
            self._span_cm = client.start_as_current_span(
                name=self.name,
                input=_maybe_redact(self.input),
                metadata={
                    **(self.metadata or {}),
                    "tags": self.tags,
                    "session_id": self.session_id,
                    "user_id": self.user_id,
                },
            )
            self._ctx = self._span_cm.__enter__()
            self._active = True
            _trace_active.set(True)
        except Exception as e:
            logger.warning(f"Failed to start trace: {e}")

    def end(
        self,
        output: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        level: Optional[str] = None,
        status_message: Optional[str] = None,
    ):
        """End the trace (exit context)."""
        if not self._active or not self._span_cm:
            return
        try:
            if self._ctx:
                if output is not None:
                    self._ctx.update(output=_maybe_redact(output))
                if metadata is not None:
                    self._ctx.update(metadata=metadata)
                if level is not None:
                    self._ctx.update(level=level)
                if status_message is not None:
                    self._ctx.update(status_message=status_message)
            self._span_cm.__exit__(None, None, None)
        except Exception as e:
            logger.warning(f"Failed to end trace: {e}")
        finally:
            self._active = False
            _trace_active.set(False)


def end_trace(
    trace,
    output: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    level: Optional[str] = None,
    status_message: Optional[str] = None,
):
    """Legacy function to end a trace."""
    if isinstance(trace, _LegacyTraceHandle):
        trace.end(output, metadata, level, status_message)


def create_generation(
    trace,
    name: str,
    model: str,
    input: Optional[str] = None,
    output: Optional[str] = None,
    usage: Optional[Dict[str, int]] = None,
    model_parameters: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    start_time: Optional[float] = None,
    end_time: Optional[float] = None,
    level: Optional[str] = None,
    status_message: Optional[str] = None,
):
    """Legacy function to create a generation span."""
    client = get_langfuse()
    if not client or not is_trace_active():
        return None

    try:
        # Use start_generation for non-context-manager usage
        generation = client.start_generation(
            name=name,
            model=model,
            input=_maybe_redact(input),
            output=_maybe_redact(output),
            model_parameters=model_parameters,
            metadata={
                **(metadata or {}),
                "latency_ms": round((end_time - start_time) * 1000, 2)
                if start_time and end_time
                else None,
            },
        )

        # Set usage if provided
        if usage:
            generation.update(
                usage_details={
                    "input": usage.get("prompt_tokens", 0),
                    "output": usage.get("completion_tokens", 0),
                    "total": usage.get("total_tokens", 0),
                }
            )

        # End the generation immediately since we have all the data
        generation.end()

        return generation
    except Exception as e:
        logger.warning(f"Failed to create generation: {e}")
        return None


def create_span(
    trace, name: str, input: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
):
    """Legacy function - use trace_span() context manager instead."""
    return None  # Not supported in legacy mode


def end_span(
    span,
    output: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    level: Optional[str] = None,
    status_message: Optional[str] = None,
):
    """Legacy function - use trace_span() context manager instead."""
    pass


def flush():
    """Flush any pending Langfuse events."""
    client = get_langfuse()
    if client:
        try:
            client.flush()
        except Exception as e:
            logger.warning(f"Failed to flush Langfuse: {e}")


def shutdown():
    """Shutdown the Langfuse client gracefully."""
    global _client
    if _client:
        try:
            _client.flush()
            _client.shutdown()
            logger.info("Langfuse client shutdown")
        except Exception as e:
            logger.warning(f"Failed to shutdown Langfuse: {e}")
        finally:
            _client = None
