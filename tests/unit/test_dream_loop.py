from dataclasses import dataclass, field
from datetime import datetime

from vecna.memory import dream_loop


@dataclass
class _FakeEvent:
    event_type: str
    payload: dict = field(default_factory=dict)
    session_id: str = "session-1"
    created_at: datetime = field(default_factory=datetime.now)


class _FakePgStore:
    def __init__(self, events, add_item_result_factory=None):
        self._events = events
        self.added_items = []
        self._add_item_result_factory = add_item_result_factory

    def get_recent_events(self, limit=100):
        return self._events[:limit]

    def search(self, query, top_k=3):
        del query
        del top_k
        return []

    def add_item(self, item):
        self.added_items.append(item)
        if self._add_item_result_factory is not None:
            return self._add_item_result_factory(item)
        return f"id-{len(self.added_items)}"


def test_run_scheduled_dream_loop_forwards_dry_run(monkeypatch):
    sentinel = object()
    received = {}

    def fake_run_dream_loop(*, dry_run):
        received["dry_run"] = dry_run
        return sentinel

    monkeypatch.setattr(dream_loop, "run_dream_loop", fake_run_dream_loop)

    result = dream_loop.run_scheduled_dream_loop(dry_run=True)

    assert received["dry_run"] is True
    assert result is sentinel


def test_generate_insights_dry_run_counts_without_writing():
    events = [
        _FakeEvent(event_type="tool_call", payload={"topic": "planning"}),
        _FakeEvent(event_type="observation", payload={"topic": "planning"}),
        _FakeEvent(event_type="observation", payload={"domain": "research"}),
    ]
    store = _FakePgStore(events)
    loop = dream_loop.DreamLoop(pg_store=store, summarizer=lambda prompt: prompt)

    count = loop._generate_insights(dry_run=True)

    assert count > 0
    assert store.added_items == []


def test_generate_insights_writes_items_when_not_dry_run():
    events = [
        _FakeEvent(event_type="tool_call", payload={"topic": "testing"}),
        _FakeEvent(event_type="observation", payload={"topic": "testing"}),
    ]
    store = _FakePgStore(events)
    loop = dream_loop.DreamLoop(pg_store=store, summarizer=lambda prompt: f"INSIGHT:{prompt}")

    count = loop._generate_insights(dry_run=False)

    assert count == 1
    assert len(store.added_items) == 1
    assert "INSIGHT:" in store.added_items[0].content


def test_generate_insights_ignores_dream_loop_events_for_pattern_detection():
    events = [
        _FakeEvent(event_type="dream_loop", payload={"topic": "meta-reflection"}),
        _FakeEvent(event_type="dream_loop", payload={"topic": "meta-reflection"}),
    ]
    store = _FakePgStore(events)
    loop = dream_loop.DreamLoop(pg_store=store)

    count = loop._generate_insights(dry_run=True)

    assert count == 0


def test_generate_insights_does_not_count_failed_add_item_writes():
    events = [
        _FakeEvent(event_type="tool_call", payload={"topic": "resilience"}),
        _FakeEvent(event_type="observation", payload={"topic": "resilience"}),
    ]
    store = _FakePgStore(events, add_item_result_factory=lambda item: None)
    loop = dream_loop.DreamLoop(pg_store=store)

    count = loop._generate_insights(dry_run=False)

    assert count == 0
    assert len(store.added_items) == 1
