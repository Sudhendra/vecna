from vecna.memory.consolidation import MemoryConsolidator
from vecna.memory.patterns import SessionPatternDetector
from vecna.memory.pg_store import MemoryItem


def test_session_pattern_detector_returns_deterministic_patterns():
    detector = SessionPatternDetector(min_count=2)
    records = [
        {"event_type": "tool_call", "payload": {"topic": "debugging"}},
        {"event_type": "observation", "payload": {"topic": "debugging"}},
        {"event_type": "observation", "payload": {"domain": "ml"}},
        {"event_type": "tool_call", "payload": {"domain": "ml"}},
    ]

    result = detector.detect(records)

    assert result["record_count"] == 4
    assert result["patterns"] == [
        {"theme": "debugging", "count": 2, "frequency": 0.5},
        {"theme": "ml", "count": 2, "frequency": 0.5},
    ]


def test_session_pattern_detector_excludes_selected_event_types():
    detector = SessionPatternDetector(min_count=2, exclude_event_types={"dream_loop"})
    records = [
        {"event_type": "dream_loop", "payload": {"topic": "meta"}},
        {"event_type": "dream_loop", "payload": {"topic": "meta"}},
        {"event_type": "observation", "payload": {"topic": "planning"}},
        {"event_type": "tool_call", "payload": {"topic": "planning"}},
    ]

    result = detector.detect(records)

    assert result["record_count"] == 2
    assert result["patterns"] == [{"theme": "planning", "count": 2, "frequency": 1.0}]


def test_memory_consolidator_merge_candidates_groups_similar_items_and_merges_group():
    consolidator = MemoryConsolidator(similarity_threshold=0.5)
    items = [
        MemoryItem(id="1", content="Build robust pytest fixtures", item_type="fact", domain="dev"),
        MemoryItem(
            id="2", content="Use pytest fixtures for robust tests", item_type="fact", domain="dev"
        ),
        MemoryItem(id="3", content="Plan migration strategy", item_type="goal", domain="ops"),
    ]

    groups = consolidator.merge_candidates(items)

    assert len(groups) == 2
    assert [item.id for item in groups[0]] == ["1", "2"]
    merged = consolidator.consolidate_group(groups[0])
    assert isinstance(merged, MemoryItem)
    assert merged.item_type == "fact"
    assert merged.domain == "dev"
    assert merged.metadata["source_ids"] == ["1", "2"]


def test_memory_consolidator_group_candidates_is_backward_compatible_alias():
    consolidator = MemoryConsolidator(similarity_threshold=0.5)
    items = [
        MemoryItem(id="1", content="Build robust pytest fixtures", item_type="fact", domain="dev"),
        MemoryItem(
            id="2", content="Use pytest fixtures for robust tests", item_type="fact", domain="dev"
        ),
        MemoryItem(id="3", content="Plan migration strategy", item_type="goal", domain="ops"),
    ]

    groups_from_merge = consolidator.merge_candidates(items)
    groups_from_group = consolidator.group_candidates(items)

    assert groups_from_group == groups_from_merge
