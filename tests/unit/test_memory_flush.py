from vecna.memory.flush import should_flush


def test_should_flush_when_near_limit():
    assert should_flush(current_tokens=9000, limit=10000, soft_threshold=500) is True
