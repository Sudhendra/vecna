"""Tests for native tool calling migration.

Validates that build_hive_update_tool_schema() produces a proper
OpenAI-style function-calling schema, and that parse_tool_call_update()
correctly converts raw tool-call dicts into HiveUpdate objects.

Amendments enforced:
- 5: Shared tool-call parsing (these are the canonical functions)
- 6: source_model field name (not "source")
- 8: Specific exceptions, no bare except
- 9: No trivial assertions — assert specific values/fields
- 10: At least 2 error/edge-case tests
- 11: Public interface only
"""

from vecna.adapters.tool_calling import (
    build_hive_update_tool_schema,
    parse_tool_call_update,
)
from vecna.core.types import HiveUpdate


class TestBuildHiveUpdateToolSchema:
    """Tests for the tool schema builder."""

    def test_schema_top_level_structure(self):
        schema = build_hive_update_tool_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "hive_update"
        assert "description" in schema["function"]
        assert len(schema["function"]["description"]) > 10  # not empty stub

    def test_schema_has_all_required_properties(self):
        schema = build_hive_update_tool_schema()
        params = schema["function"]["parameters"]
        assert params["type"] == "object"

        expected_properties = {
            "new_facts",
            "belief_changes",
            "hypotheses",
            "open_questions",
            "contradictions",
            "overall_confidence",
            "user_preferences_observed",
        }
        actual_properties = set(params["properties"].keys())
        assert expected_properties == actual_properties

    def test_schema_new_facts_item_structure(self):
        schema = build_hive_update_tool_schema()
        facts_prop = schema["function"]["parameters"]["properties"]["new_facts"]
        assert facts_prop["type"] == "array"
        item_props = facts_prop["items"]["properties"]
        assert "content" in item_props
        assert "confidence" in item_props
        assert "evidence" in item_props
        assert "domain" in item_props
        # content must be required
        assert "content" in facts_prop["items"]["required"]

    def test_schema_belief_changes_item_structure(self):
        schema = build_hive_update_tool_schema()
        beliefs_prop = schema["function"]["parameters"]["properties"]["belief_changes"]
        assert beliefs_prop["type"] == "array"
        item_props = beliefs_prop["items"]["properties"]
        assert "content" in item_props
        assert "confidence" in item_props
        assert "reasoning" in item_props
        assert "content" in beliefs_prop["items"]["required"]

    def test_schema_hypotheses_item_structure(self):
        schema = build_hive_update_tool_schema()
        hypo_prop = schema["function"]["parameters"]["properties"]["hypotheses"]
        assert hypo_prop["type"] == "array"
        item_props = hypo_prop["items"]["properties"]
        assert "content" in item_props
        assert "confidence" in item_props
        assert "notes" in item_props
        assert "content" in hypo_prop["items"]["required"]

    def test_schema_contradictions_item_structure(self):
        schema = build_hive_update_tool_schema()
        contra_prop = schema["function"]["parameters"]["properties"]["contradictions"]
        assert contra_prop["type"] == "array"
        item_props = contra_prop["items"]["properties"]
        assert "item_a" in item_props
        assert "item_b" in item_props
        assert set(contra_prop["items"]["required"]) == {"item_a", "item_b"}

    def test_schema_overall_confidence_is_number(self):
        schema = build_hive_update_tool_schema()
        conf_prop = schema["function"]["parameters"]["properties"]["overall_confidence"]
        assert conf_prop["type"] == "number"

    def test_schema_is_deterministic(self):
        """Calling build twice returns identical schemas."""
        schema1 = build_hive_update_tool_schema()
        schema2 = build_hive_update_tool_schema()
        assert schema1 == schema2


class TestParseToolCallUpdate:
    """Tests for parsing tool-call dicts into HiveUpdate objects."""

    def test_parse_full_tool_call(self):
        tool_call_args = {
            "new_facts": [
                {"content": "Python is interpreted", "confidence": 0.9, "domain": "programming"}
            ],
            "belief_changes": [{"content": "Python is good for beginners", "confidence": 0.8}],
            "hypotheses": [{"content": "Python 4 may add static typing", "confidence": 0.3}],
            "open_questions": [{"question": "Will GIL be removed?", "priority": "high"}],
            "contradictions": [{"item_a": "Python is slow", "item_b": "Python is fast enough"}],
            "overall_confidence": 0.85,
        }
        update = parse_tool_call_update(tool_call_args, source_model="gpt-5.2")

        assert update.source_model == "gpt-5.2"
        assert update.confidence == 0.85
        assert len(update.new_facts) == 1
        assert update.new_facts[0]["content"] == "Python is interpreted"
        assert update.new_facts[0]["confidence"] == 0.9
        assert update.new_facts[0]["domain"] == "programming"
        assert len(update.belief_changes) == 1
        assert update.belief_changes[0]["content"] == "Python is good for beginners"
        assert len(update.new_hypotheses) == 1
        assert update.new_hypotheses[0]["content"] == "Python 4 may add static typing"
        assert len(update.open_questions) == 1
        assert update.open_questions[0]["question"] == "Will GIL be removed?"
        assert len(update.contradictions_found) == 1
        assert update.contradictions_found[0]["item_a"] == "Python is slow"

    def test_parse_empty_tool_call(self):
        update = parse_tool_call_update({}, source_model="test-model")
        assert update.source_model == "test-model"
        assert len(update.new_facts) == 0
        assert len(update.belief_changes) == 0
        assert len(update.new_hypotheses) == 0
        assert len(update.open_questions) == 0
        assert len(update.contradictions_found) == 0
        # Default confidence should remain 0.5 when not provided
        assert update.confidence == 0.5

    def test_parse_preserves_source_model_field_name(self):
        """Amendment 6: field is source_model, not source."""
        update = parse_tool_call_update(
            {"new_facts": [{"content": "test"}]},
            source_model="claude-3.5",
        )
        assert update.source_model == "claude-3.5"
        # Verify the field actually exists on HiveUpdate (not a dynamic attr)
        assert "source_model" in {f.name for f in update.__dataclass_fields__.values()}

    def test_parse_multiple_facts(self):
        tool_call_args = {
            "new_facts": [
                {"content": "Fact A", "confidence": 0.7},
                {"content": "Fact B", "confidence": 0.8},
                {"content": "Fact C", "confidence": 0.95},
            ],
        }
        update = parse_tool_call_update(tool_call_args, source_model="multi-model")
        assert len(update.new_facts) == 3
        assert update.new_facts[0]["content"] == "Fact A"
        assert update.new_facts[1]["content"] == "Fact B"
        assert update.new_facts[2]["content"] == "Fact C"
        assert update.new_facts[2]["confidence"] == 0.95

    def test_parse_null_lists_become_empty(self):
        """Models may return null instead of empty arrays."""
        tool_call_args = {
            "new_facts": None,
            "belief_changes": None,
            "hypotheses": None,
            "open_questions": None,
            "contradictions": None,
        }
        update = parse_tool_call_update(tool_call_args, source_model="null-model")
        assert update.new_facts == []
        assert update.belief_changes == []
        assert update.new_hypotheses == []
        assert update.open_questions == []
        assert update.contradictions_found == []


class TestParseToolCallEdgeCases:
    """Error and edge-case tests (Amendment 10)."""

    def test_parse_invalid_confidence_string(self):
        """Models may return confidence as a non-numeric string."""
        tool_call_args = {
            "overall_confidence": "very high",
        }
        update = parse_tool_call_update(tool_call_args, source_model="bad-model")
        # Should keep default confidence, not crash
        assert update.confidence == 0.5

    def test_parse_confidence_out_of_range_clamped(self):
        """Confidence values outside 0-1 should be clamped."""
        tool_call_args_high = {"overall_confidence": 1.5}
        update_high = parse_tool_call_update(tool_call_args_high, source_model="test")
        assert update_high.confidence == 1.0

        tool_call_args_low = {"overall_confidence": -0.3}
        update_low = parse_tool_call_update(tool_call_args_low, source_model="test")
        assert update_low.confidence == 0.0

    def test_parse_confidence_none_keeps_default(self):
        """Explicit None for confidence should keep default."""
        tool_call_args = {"overall_confidence": None}
        update = parse_tool_call_update(tool_call_args, source_model="test")
        assert update.confidence == 0.5

    def test_parse_extra_unknown_fields_ignored(self):
        """Models may include extra fields not in schema; don't crash."""
        tool_call_args = {
            "new_facts": [{"content": "Real fact"}],
            "unknown_field": "should be ignored",
            "another_unexpected": [1, 2, 3],
        }
        update = parse_tool_call_update(tool_call_args, source_model="creative-model")
        assert len(update.new_facts) == 1
        assert update.new_facts[0]["content"] == "Real fact"

    def test_parse_confidence_as_integer(self):
        """Models may return confidence as int (1 instead of 1.0)."""
        tool_call_args = {"overall_confidence": 1}
        update = parse_tool_call_update(tool_call_args, source_model="int-model")
        assert update.confidence == 1.0

    def test_parse_user_preferences_observed(self):
        """Verify user_preferences_observed are parsed when present."""
        tool_call_args = {
            "user_preferences_observed": [
                {"key": "code_style", "value": "functional", "confidence": 0.8},
                {"key": "language", "value": "python", "confidence": 0.95},
            ],
        }
        update = parse_tool_call_update(tool_call_args, source_model="pref-model")
        assert len(update.user_preferences_observed) == 2
        assert update.user_preferences_observed[0]["key"] == "code_style"
        assert update.user_preferences_observed[1]["value"] == "python"

    def test_parse_returns_hive_update_with_correct_type(self):
        """Ensure parse always returns a proper HiveUpdate, not a dict or subclass."""
        update = parse_tool_call_update(
            {"new_facts": [{"content": "x"}]},
            source_model="type-check",
        )
        assert type(update) is HiveUpdate
        assert update.source_model == "type-check"

    def test_parse_non_dict_args_raises_type_error(self):
        """Error path: args must be a dict."""
        import pytest

        with pytest.raises(TypeError, match="args must be a dict"):
            parse_tool_call_update(["not", "a", "dict"], source_model="model")  # type: ignore[arg-type]

    def test_parse_empty_source_model_raises_value_error(self):
        """Error path: source_model must be non-empty."""
        import pytest

        with pytest.raises(ValueError, match="source_model must be a non-empty string"):
            parse_tool_call_update({}, source_model="")

    def test_parse_nan_confidence_keeps_default(self):
        """NaN confidence should be treated as invalid and keep default."""
        update = parse_tool_call_update({"overall_confidence": "nan"}, source_model="nan-model")
        assert update.confidence == 0.5

    def test_parse_infinite_confidence_keeps_default(self):
        """Infinite confidence should be treated as invalid and keep default."""
        update = parse_tool_call_update(
            {"overall_confidence": float("inf")}, source_model="inf-model"
        )
        assert update.confidence == 0.5
