"""Provider SDK exception discovery for orchestration fallback paths."""

from typing import List, Tuple, Type


def _collect_provider_api_errors() -> Tuple[Type[BaseException], ...]:
    errors: List[Type[BaseException]] = []

    def _append(exc_type: object) -> None:
        if isinstance(exc_type, type) and issubclass(exc_type, BaseException):
            if exc_type not in errors:
                errors.append(exc_type)

    try:
        import openai  # type: ignore

        for name in (
            "APIError",
            "RateLimitError",
            "APITimeoutError",
            "AuthenticationError",
            "BadRequestError",
        ):
            _append(getattr(openai, name, None))
    except ImportError:
        pass

    try:
        import anthropic  # type: ignore

        for name in (
            "APIError",
            "RateLimitError",
            "APITimeoutError",
            "AuthenticationError",
            "BadRequestError",
        ):
            _append(getattr(anthropic, name, None))
    except ImportError:
        pass

    return tuple(errors)


PROVIDER_API_ERRORS: Tuple[Type[BaseException], ...] = _collect_provider_api_errors()
