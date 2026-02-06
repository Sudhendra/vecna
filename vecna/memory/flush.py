def should_flush(current_tokens: int, limit: int, soft_threshold: int) -> bool:
    return (limit - current_tokens) <= soft_threshold


def estimate_token_count(text: str) -> int:
    """Estimate tokens as rounded-up characters per four."""
    if not text:
        return 0
    return (len(text) + 3) // 4
