def should_flush(current_tokens: int, limit: int, soft_threshold: int) -> bool:
    return (limit - current_tokens) <= soft_threshold


def estimate_token_count(text: str) -> int:
    if not text:
        return 0
    return len(text) // 4
