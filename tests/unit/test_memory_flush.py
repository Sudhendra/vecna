from vecna.memory.flush import estimate_token_count, should_flush


def test_should_flush_when_near_limit():
    assert should_flush(current_tokens=9700, limit=10000, soft_threshold=500) is True


def test_should_not_flush_when_far_from_limit():
    assert should_flush(current_tokens=2000, limit=10000, soft_threshold=500) is False


def test_estimate_token_count_splits_on_whitespace():
    assert estimate_token_count("one two") == 2
