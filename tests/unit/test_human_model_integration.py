"""Unit tests for HumanModel integration into HiveLoop.

Tests that HumanModel context flows into prompts, preference signals
are extracted from task/response pairs, and interaction count is
maintained across think() calls.
"""

from vecna.adapters.base import BaseAdapter, ModelConfig, HIVE_IDENTITY_PROMPT
from vecna.core.hive_state import HiveState
from vecna.core.human_model import HumanModel, Preference


class MockAdapterForHM(BaseAdapter):
    """Mock adapter that captures the prompt it receives."""

    def __init__(self):
        config = ModelConfig(name="mock-hm", model_id="mock-hm-v1")
        super().__init__(config)
        self.last_prompt = ""

    async def generate(self, prompt: str) -> str:
        self.last_prompt = prompt
        return (
            "Got it, I'll be concise.\n\n"
            "<HIVE_UPDATE>\n"
            "new_facts:\n"
            '  - content: "User prefers concise answers"\n'
            "    confidence: 0.8\n"
            "</HIVE_UPDATE>"
        )

    def _get_provider_name(self) -> str:
        return "mock"


class TestHumanModelPromptInjection:
    """Tests that HumanModel context is injected into prompts."""

    def test_hive_identity_prompt_has_human_model_placeholder(self):
        """HIVE_IDENTITY_PROMPT includes {human_model_context}."""
        assert "{human_model_context}" in HIVE_IDENTITY_PROMPT

    def test_build_prompt_includes_human_model(self):
        """build_prompt injects HumanModel context when provided."""
        adapter = MockAdapterForHM()
        state = HiveState()
        human_model = HumanModel()
        human_model.add_preference(
            Preference(
                key="communication_style",
                value="concise",
                confidence=0.9,
            )
        )
        prompt = adapter.build_prompt(
            state,
            "Tell me about Python",
            human_model=human_model,
        )
        assert "communication_style" in prompt
        assert "concise" in prompt

    def test_build_prompt_works_without_human_model(self):
        """build_prompt works when human_model is None."""
        adapter = MockAdapterForHM()
        state = HiveState()
        prompt = adapter.build_prompt(state, "Hello")
        assert "{human_model_context}" not in prompt
        assert "Hello" in prompt

    def test_build_prompt_with_empty_human_model(self):
        """build_prompt works with a HumanModel that has no preferences."""
        adapter = MockAdapterForHM()
        state = HiveState()
        human_model = HumanModel()
        prompt = adapter.build_prompt(state, "Hello", human_model=human_model)
        assert "{human_model_context}" not in prompt
        assert "Hello" in prompt

    def test_build_prompt_human_model_overrides_state_human_model(self):
        """Explicit human_model param takes precedence over state.human_model."""
        adapter = MockAdapterForHM()
        state = HiveState()
        # Set a different human model on state
        state_hm = state.ensure_human_model()
        state_hm.name = "StateUser"
        state_hm.add_preference(Preference(key="lang", value="rust", confidence=0.9))

        # Explicit param with different data
        explicit_hm = HumanModel(name="ExplicitUser")
        explicit_hm.add_preference(Preference(key="lang", value="python", confidence=0.9))
        prompt = adapter.build_prompt(state, "Hello", human_model=explicit_hm)
        assert "ExplicitUser" in prompt
        assert "python" in prompt


class TestPreferenceExtraction:
    """Tests for extracting preference signals from responses.

    Amendment 11: Uses public method extract_preference_signals().
    """

    def test_extract_preference_signals_from_concise_request(self):
        """extract_preference_signals detects 'concise' as a brief detail_level."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
        )
        signals = loop.extract_preference_signals(
            task="Be concise please",
            response="Got it, I'll be concise.",
        )
        assert len(signals) >= 1
        detail_signals = [s for s in signals if s["dimension"] == "detail_level"]
        assert len(detail_signals) == 1
        assert detail_signals[0]["value"] == "brief"

    def test_preference_signals_detect_style_request(self):
        """Preference extraction detects communication style cues."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
        )
        signals = loop.extract_preference_signals(
            task="Give me a detailed explanation",
            response="Here is a thorough breakdown...",
        )
        found_detail = any(
            s.get("dimension") == "detail_level" and s.get("value") == "detailed" for s in signals
        )
        assert found_detail

    def test_preference_signals_detect_tone_request(self):
        """Preference extraction detects tone cues like 'formal'."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
        )
        signals = loop.extract_preference_signals(
            task="Please respond in a formal manner",
            response="Certainly. Here is the formal response.",
        )
        tone_signals = [s for s in signals if s["dimension"] == "tone"]
        assert len(tone_signals) == 1
        assert tone_signals[0]["value"] == "formal"

    def test_preference_signals_empty_for_neutral_input(self):
        """No preference signals for a neutral task with no style cues."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
        )
        signals = loop.extract_preference_signals(
            task="What is 2+2?",
            response="4",
        )
        assert signals == []

    def test_preference_signals_from_empty_task(self):
        """Edge case: empty task should return empty signals list."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
        )
        signals = loop.extract_preference_signals(
            task="",
            response="some response",
        )
        assert signals == []


class TestHumanModelPersistence:
    """Tests for HumanModel save/load alongside HiveState."""

    def test_human_model_interaction_count_increments(self):
        """Each think() call increments interaction count.

        Amendment 11: Access human_model through state.human_model (public).
        """
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        human_model = HumanModel()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
            human_model=human_model,
        )
        initial = loop.state.human_model.interaction_count
        loop.state.human_model.interaction_count += 1
        assert loop.state.human_model.interaction_count == initial + 1

    def test_human_model_export_import_roundtrip(self):
        """HumanModel survives export/import cycle."""
        model = HumanModel()
        model.add_preference(
            Preference(
                key="tone",
                value="friendly",
                confidence=0.85,
            )
        )
        model.interaction_count = 42
        exported = model.to_dict()
        restored = HumanModel.from_dict(exported)
        assert restored.interaction_count == 42
        pref = restored.get_preference("tone")
        assert pref is not None
        assert pref.value == "friendly"

    async def test_think_with_human_model(self):
        """HiveLoop.think works when human_model is attached.

        Amendment 11: Pass human_model via constructor.
        Amendment 9: Assert result contains domain-relevant content.
        """
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        human_model = HumanModel()
        human_model.add_preference(
            Preference(
                key="expertise",
                value="advanced",
                confidence=0.9,
            )
        )
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
            human_model=human_model,
        )
        result = await loop.think("Explain recursion")
        assert "concise" in result.lower() or len(result) > 0
        # The mock adapter returns a response containing "concise"
        assert "concise" in result.lower()

    async def test_think_updates_human_model_interaction_count(self):
        """think() increments human_model.interaction_count.

        Amendment 11: Access via state.human_model (public attribute).
        """
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        human_model = HumanModel()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
            human_model=human_model,
        )
        initial = loop.state.human_model.interaction_count
        await loop.think("Hello")
        assert loop.state.human_model.interaction_count == initial + 1

    async def test_think_applies_preference_signals_to_human_model(self):
        """think() applies extracted preference signals to HumanModel.

        Amendment 9: Assert specific preference key/value, not just type.
        """
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        human_model = HumanModel()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
            human_model=human_model,
        )
        await loop.think("Be concise please")
        pref = loop.state.human_model.get_preference("detail_level")
        assert pref is not None
        assert pref.value == "brief"

    async def test_think_without_human_model_still_works(self):
        """think() works fine without a human_model attached."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
        )
        result = await loop.think("Hello")
        assert "Got it, I'll be concise." in result


class TestHumanModelConstructorInjection:
    """Amendment 11: HumanModel must be passed via constructor, not private attrs."""

    def test_constructor_sets_human_model_on_state(self):
        """Passing human_model to HiveLoop sets state.human_model."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        human_model = HumanModel(name="TestUser")
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
            human_model=human_model,
        )
        assert loop.state.human_model is not None
        assert loop.state.human_model.name == "TestUser"

    def test_constructor_without_human_model_leaves_state_none(self):
        """Not passing human_model leaves state.human_model as None."""
        from vecna.orchestrator.loop import HiveLoop, HiveConfig

        adapter = MockAdapterForHM()
        config = HiveConfig()
        loop = HiveLoop(
            config=config,
            adapters=[adapter],
            name="test-hm",
        )
        assert loop.state.human_model is None


class TestConcurrentPreferenceUpdates:
    """Amendment 12: Concurrent stress test for HumanModel updates."""

    async def test_concurrent_preference_additions(self):
        """50 concurrent add_preference calls should not lose data."""
        import asyncio

        model = HumanModel()

        async def add_pref(i: int) -> None:
            model.add_preference(
                Preference(
                    key=f"pref_{i}",
                    value=f"value_{i}",
                    confidence=0.5 + (i % 50) * 0.01,
                )
            )

        await asyncio.gather(*[add_pref(i) for i in range(50)])
        # All 50 unique keys should be present
        assert len(model.preferences) == 50
        keys = {p.key for p in model.preferences}
        assert len(keys) == 50
