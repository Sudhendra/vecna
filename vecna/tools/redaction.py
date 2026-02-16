"""Utilities for redacting secrets and PII from logs."""

import re
from typing import Any, Callable, Match, Optional, Pattern

SECRET_PLACEHOLDER = "[REDACTED_SECRET]"
PII_PLACEHOLDER = "[REDACTED_PII]"

RedactReplacement = Callable[[Match[str]], str]


_SECRET_REPLACEMENTS: list[tuple[Pattern[str], RedactReplacement]] = [
    (
        re.compile(
            r"(?i)\b(password|passwd|pwd|api[_-]?key|token|secret|authorization)\b\s*[:=]\s*([^\s,;]+)"
        ),
        lambda match: f"{match.group(1)}={SECRET_PLACEHOLDER}",
    ),
    (re.compile(r"(?i)\bbearer\s+[a-z0-9\-._~+/]+=*"), lambda match: SECRET_PLACEHOLDER),
    (re.compile(r"\bsk-[a-zA-Z0-9_-]{8,}\b"), lambda match: SECRET_PLACEHOLDER),
]

_PII_REPLACEMENTS: list[tuple[Pattern[str], RedactReplacement]] = [
    (
        re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"),
        lambda match: PII_PLACEHOLDER,
    ),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), lambda match: PII_PLACEHOLDER),
    (
        re.compile(r"\b(?:\+?\d{1,2}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]\d{4}\b"),
        lambda match: PII_PLACEHOLDER,
    ),
]

_SECRET_KEY_PATTERN = re.compile(
    r"(?i)(password|passwd|pwd|api[_-]?key|token|secret|authorization)"
)
_PII_KEY_PATTERN = re.compile(r"(?i)(email|phone|ssn)")


def _apply_patterns(text: str, replacements: list[tuple[Pattern[str], RedactReplacement]]) -> str:
    redacted = text
    for pattern, replacement in replacements:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _walk_and_redact(
    value: Any,
    redactor,
    key_pattern: Optional[Pattern[str]] = None,
    key_placeholder: Optional[str] = None,
) -> Any:
    if isinstance(value, str):
        return redactor(value)
    if isinstance(value, list):
        return [
            _walk_and_redact(
                item, redactor, key_pattern=key_pattern, key_placeholder=key_placeholder
            )
            for item in value
        ]
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if (
                key_pattern is not None
                and key_placeholder is not None
                and isinstance(item, str)
                and key_pattern.search(str(key))
            ):
                redacted[key] = key_placeholder
            else:
                redacted[key] = _walk_and_redact(
                    item,
                    redactor,
                    key_pattern=key_pattern,
                    key_placeholder=key_placeholder,
                )
        return redacted
    return value


def redact_secrets(value: Any) -> Any:
    """Redact likely secrets (tokens, passwords, API keys) in text or nested data."""
    return _walk_and_redact(
        value,
        lambda text: _apply_patterns(text, _SECRET_REPLACEMENTS),
        key_pattern=_SECRET_KEY_PATTERN,
        key_placeholder=SECRET_PLACEHOLDER,
    )


def redact_pii(value: Any) -> Any:
    """Redact likely PII (email, phone, SSN) in text or nested data."""
    return _walk_and_redact(
        value,
        lambda text: _apply_patterns(text, _PII_REPLACEMENTS),
        key_pattern=_PII_KEY_PATTERN,
        key_placeholder=PII_PLACEHOLDER,
    )


def redact_all(value: Any) -> Any:
    """Redact secrets and PII in text or nested data."""
    return redact_pii(redact_secrets(value))
