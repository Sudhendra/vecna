from vecna.memory.flush import estimate_token_count, should_flush


def test_should_flush_when_near_limit():
    assert should_flush(current_tokens=9700, limit=10000, soft_threshold=500) is True


def test_should_not_flush_when_far_from_limit():
    assert should_flush(current_tokens=2000, limit=10000, soft_threshold=500) is False


def test_estimate_token_count_uses_character_heuristic():
    assert estimate_token_count("") == 0
    assert estimate_token_count("a") == 1
    assert estimate_token_count("abcd") == (len("abcd") + 3) // 4
    assert estimate_token_count("a" * 20) == (len("a" * 20) + 3) // 4
