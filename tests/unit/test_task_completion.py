"""Tests for task completion detection."""

import pytest


class TestTaskCompletion:
    def test_direct_answer_is_complete(self):
        """A direct factual answer should be considered complete."""
        from vecna.orchestrator.loop import is_task_complete

        response = "Python was created by Guido van Rossum in 1991."
        task = "Who created Python?"
        assert is_task_complete(response, task, cycle=1, max_cycles=10)

    def test_question_back_is_not_complete(self):
        """If the response asks a clarifying question, task isn't complete."""
        from vecna.orchestrator.loop import is_task_complete

        response = "Could you clarify what you mean by 'fast'?"
        task = "Is Python fast?"
        assert not is_task_complete(response, task, cycle=1, max_cycles=10)

    def test_max_cycles_forces_completion(self):
        """At max cycles, always return True to prevent infinite loops."""
        from vecna.orchestrator.loop import is_task_complete

        response = "Still thinking..."
        task = "Complex task"
        assert is_task_complete(response, task, cycle=10, max_cycles=10)

    def test_empty_response_not_complete(self):
        """An empty response should never be considered complete."""
        from vecna.orchestrator.loop import is_task_complete

        assert not is_task_complete("", "Do something", cycle=1, max_cycles=10)

    def test_tool_call_pending_not_complete(self):
        """A response indicating pending action should not be complete on early cycles."""
        from vecna.orchestrator.loop import is_task_complete

        response = "Let me search for that information."
        task = "Find the latest Python release"
        # First cycle with action words = not complete
        assert not is_task_complete(response, task, cycle=1, max_cycles=10)


class TestTaskCompletionEdgeCases:
    """Edge cases and error paths for task completion detection (Amendment 10)."""

    def test_whitespace_only_response_not_complete(self):
        """A whitespace-only response should not be considered complete."""
        from vecna.orchestrator.loop import is_task_complete

        assert not is_task_complete("   \n\t  ", "Do something", cycle=1, max_cycles=10)

    def test_very_short_response_not_complete(self):
        """A response with fewer than 3 words should not be considered complete."""
        from vecna.orchestrator.loop import is_task_complete

        assert not is_task_complete("Yes.", "Is Python good?", cycle=1, max_cycles=10)

    def test_action_intent_near_max_cycles_is_complete(self):
        """Action intent on the penultimate cycle should be treated as complete."""
        from vecna.orchestrator.loop import is_task_complete

        response = "Let me search for that information and provide details."
        task = "Find info"
        # At cycle=max_cycles-1, action indicators are NOT checked (safety valve near end)
        assert is_task_complete(response, task, cycle=9, max_cycles=10)

    def test_multiple_question_indicators_not_complete(self):
        """Response with 'would you like' variant should not be complete."""
        from vecna.orchestrator.loop import is_task_complete

        response = "Would you like me to explain this in more detail?"
        task = "Explain Python decorators"
        assert not is_task_complete(response, task, cycle=1, max_cycles=10)

    def test_should_i_question_not_complete(self):
        """Response with 'should i' should not be complete."""
        from vecna.orchestrator.loop import is_task_complete

        response = "Should I proceed with the installation?"
        task = "Install Python"
        assert not is_task_complete(response, task, cycle=1, max_cycles=10)

    def test_substantive_multi_sentence_response_is_complete(self):
        """A substantive multi-sentence answer should be considered complete."""
        from vecna.orchestrator.loop import is_task_complete

        response = (
            "Python is a high-level, interpreted programming language. "
            "It was created by Guido van Rossum and first released in 1991. "
            "Python emphasizes code readability with its notable use of significant whitespace."
        )
        task = "Tell me about Python"
        assert is_task_complete(response, task, cycle=1, max_cycles=10)

    def test_cycle_zero_with_direct_answer_is_complete(self):
        """Even at cycle 0, a direct answer should be considered complete."""
        from vecna.orchestrator.loop import is_task_complete

        response = "The capital of France is Paris, a major European city."
        task = "What is the capital of France?"
        assert is_task_complete(response, task, cycle=0, max_cycles=10)

    def test_max_cycles_one_forces_completion(self):
        """When max_cycles=1, cycle=1 should force completion even with bad response."""
        from vecna.orchestrator.loop import is_task_complete

        response = "Could you clarify what you mean?"
        task = "Something"
        assert is_task_complete(response, task, cycle=1, max_cycles=1)

    def test_invalid_response_type_raises_type_error(self):
        """Error path: response must be a string."""
        from vecna.orchestrator.loop import is_task_complete

        with pytest.raises(TypeError, match="response must be a string"):
            is_task_complete(None, "task", cycle=1, max_cycles=10)  # type: ignore[arg-type]

    def test_non_positive_max_cycles_raises_value_error(self):
        """Error path: max_cycles must be positive."""
        from vecna.orchestrator.loop import is_task_complete

        with pytest.raises(ValueError, match="max_cycles must be positive"):
            is_task_complete("ok", "task", cycle=0, max_cycles=0)
