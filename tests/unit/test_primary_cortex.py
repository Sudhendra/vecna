"""Tests for Primary Cortex model hierarchy.

The Primary Cortex architecture replaces the naive max(responses, key=len)
response selection with a hierarchy: the highest-weight model is the Primary
Cortex, and all others are Advisory Lenses consulted for disagreement signals.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from vecna.orchestrator.loop import HiveConfig, HiveLoop, select_best_response


# ============================================================
# Helpers
# ============================================================


def _make_adapter(name: str, weight: float, domain: str = "general") -> MagicMock:
    """Build a mock adapter with the fields HiveLoop inspects."""
    adapter = MagicMock()
    adapter.name = name
    adapter.weight = weight
    adapter.domain = domain
    return adapter


# ============================================================
# TestPrimaryCortexSelection
# ============================================================


class TestPrimaryCortexSelection:
    """Tests for get_primary_cortex() and get_advisory_lenses()."""

    def test_highest_weight_is_primary(self):
        """Primary cortex is the adapter with the highest weight."""
        config = HiveConfig()
        loop = HiveLoop(config=config)
        loop.adapters = [
            _make_adapter("gpt-4o-mini", weight=0.8),
            _make_adapter("gpt-5.2", weight=2.0),
            _make_adapter("gpt-4.1", weight=1.0),
        ]

        primary = loop.get_primary_cortex()
        assert primary.name == "gpt-5.2"
        assert primary.weight == 2.0

    def test_advisory_lenses_exclude_primary(self):
        """Advisory lenses are all adapters except the primary cortex."""
        config = HiveConfig()
        loop = HiveLoop(config=config)
        loop.adapters = [
            _make_adapter("primary", weight=2.0),
            _make_adapter("lens1", weight=1.0),
            _make_adapter("lens2", weight=0.8),
        ]

        lenses = loop.get_advisory_lenses()
        lens_names = [lens.name for lens in lenses]
        assert lens_names == ["lens1", "lens2"]
        assert "primary" not in lens_names

    def test_single_adapter_is_primary(self):
        """When only one adapter exists, it is both primary and the only cortex."""
        config = HiveConfig()
        loop = HiveLoop(config=config)
        loop.adapters = [_make_adapter("solo", weight=1.0)]

        primary = loop.get_primary_cortex()
        assert primary.name == "solo"

        lenses = loop.get_advisory_lenses()
        assert lenses == []

    def test_no_adapters_returns_none(self):
        """get_primary_cortex returns None when no adapters are configured."""
        config = HiveConfig()
        loop = HiveLoop(config=config)
        loop.adapters = []

        assert loop.get_primary_cortex() is None
        assert loop.get_advisory_lenses() == []

    def test_equal_weights_picks_first_max(self):
        """When weights are equal, max() picks the first occurrence deterministically."""
        config = HiveConfig()
        loop = HiveLoop(config=config)
        loop.adapters = [
            _make_adapter("alpha", weight=1.0),
            _make_adapter("beta", weight=1.0),
        ]

        primary = loop.get_primary_cortex()
        # max() with key returns first element when equal — deterministic
        assert primary.name == "alpha"


# ============================================================
# TestSelectBestResponse
# ============================================================


class TestSelectBestResponse:
    """Tests for the select_best_response() module-level function."""

    def test_primary_response_preferred_when_present(self):
        """When primary has a response, it wins regardless of length."""
        responses = {
            "primary": "Python uses dynamic typing for flexibility.",
            "lens1": "Python's typing is dynamic and quite flexible with many features.",
            "lens2": "Python has dynamic types.",
        }
        best = select_best_response(responses, primary_name="primary")
        assert best == "Python uses dynamic typing for flexibility."

    def test_fallback_to_longest_when_primary_missing(self):
        """When primary has no response, fall back to the longest response."""
        responses = {
            "lens1": "Short answer.",
            "lens2": "This is a much longer and more detailed response to the question.",
        }
        best = select_best_response(responses, primary_name="primary")
        assert best == "This is a much longer and more detailed response to the question."

    def test_fallback_when_primary_response_empty(self):
        """When primary exists but response is whitespace-only, fall back."""
        responses = {
            "primary": "   ",
            "lens1": "Actual response content here.",
        }
        best = select_best_response(responses, primary_name="primary")
        assert best == "Actual response content here."

    def test_empty_responses_dict_returns_empty_string(self):
        """Empty responses dict returns empty string, no crash."""
        best = select_best_response({}, primary_name="primary")
        assert best == ""

    def test_all_responses_empty_returns_empty(self):
        """When all responses are empty strings, return empty string."""
        responses = {
            "primary": "",
            "lens1": "",
        }
        best = select_best_response(responses, primary_name="primary")
        assert best == ""


# ============================================================
# TestCircuitBreaker
# ============================================================


class TestCircuitBreaker:
    """Tests for per-adapter CircuitBreaker (Amendment 13)."""

    def test_breaker_closed_initially(self):
        """A new circuit breaker starts in closed state (allowing requests)."""
        from vecna.orchestrator.loop import CircuitBreaker

        breaker = CircuitBreaker(adapter_name="test-adapter")
        assert breaker.is_open() is False
        assert breaker.failure_count == 0

    def test_breaker_opens_after_max_failures(self):
        """Circuit breaker opens after N consecutive failures (default 3)."""
        from vecna.orchestrator.loop import CircuitBreaker

        breaker = CircuitBreaker(adapter_name="test-adapter", max_failures=3)
        breaker.record_failure()
        assert breaker.is_open() is False
        breaker.record_failure()
        assert breaker.is_open() is False
        breaker.record_failure()
        assert breaker.is_open() is True

    def test_breaker_resets_on_success(self):
        """A successful call resets the failure count and closes the breaker."""
        from vecna.orchestrator.loop import CircuitBreaker

        breaker = CircuitBreaker(adapter_name="test-adapter", max_failures=3)
        breaker.record_failure()
        breaker.record_failure()
        assert breaker.failure_count == 2

        breaker.record_success()
        assert breaker.failure_count == 0
        assert breaker.is_open() is False

    def test_breaker_exponential_cooldown(self):
        """Cooldown increases exponentially: 30s, 60s, 120s, capped at 300s."""
        from vecna.orchestrator.loop import CircuitBreaker

        breaker = CircuitBreaker(
            adapter_name="test-adapter",
            max_failures=3,
            base_cooldown=30.0,
            max_cooldown=300.0,
        )
        # Trip the breaker (3 failures)
        for _ in range(3):
            breaker.record_failure()

        # First cooldown should be 30s (base_cooldown * 2^0)
        assert breaker.cooldown_until is not None
        expected_min = datetime.now() + timedelta(seconds=28)
        expected_max = datetime.now() + timedelta(seconds=32)
        assert expected_min <= breaker.cooldown_until <= expected_max

    def test_breaker_cooldown_capped_at_max(self):
        """Cooldown never exceeds max_cooldown."""
        from vecna.orchestrator.loop import CircuitBreaker

        breaker = CircuitBreaker(
            adapter_name="test-adapter",
            max_failures=3,
            base_cooldown=30.0,
            max_cooldown=300.0,
        )
        # Many failures to push cooldown past cap
        for _ in range(20):
            breaker.record_failure()

        assert breaker.cooldown_until is not None
        max_allowed = datetime.now() + timedelta(seconds=302)
        assert breaker.cooldown_until <= max_allowed

    def test_breaker_half_open_after_cooldown_expires(self):
        """After cooldown expires, breaker enters half-open state (allows retry)."""
        from vecna.orchestrator.loop import CircuitBreaker

        breaker = CircuitBreaker(adapter_name="test-adapter", max_failures=3)
        for _ in range(3):
            breaker.record_failure()
        assert breaker.is_open() is True

        # Simulate cooldown expiration
        breaker.cooldown_until = datetime.now() - timedelta(seconds=1)
        assert breaker.is_open() is False  # Half-open: allows retry

    def test_breaker_custom_max_failures(self):
        """Circuit breaker respects custom max_failures threshold."""
        from vecna.orchestrator.loop import CircuitBreaker

        breaker = CircuitBreaker(adapter_name="test-adapter", max_failures=5)
        for _ in range(4):
            breaker.record_failure()
        assert breaker.is_open() is False

        breaker.record_failure()
        assert breaker.is_open() is True


# ============================================================
# TestCallAdapterWithTimeout
# ============================================================


class TestCallAdapterWithTimeout:
    """Tests for _call_adapter_with_timeout with circuit breaker integration."""

    async def test_skips_adapter_when_breaker_open(self):
        """When circuit breaker is open, adapter call is skipped (returns None)."""
        from vecna.orchestrator.loop import CircuitBreaker

        config = HiveConfig()
        loop = HiveLoop(config=config)

        adapter = _make_adapter("broken-adapter", weight=1.0)
        breaker = CircuitBreaker(adapter_name="broken-adapter", max_failures=3)
        for _ in range(3):
            breaker.record_failure()

        loop._circuit_breakers = {"broken-adapter": breaker}

        result = await loop._call_adapter_with_timeout(adapter, "test prompt")
        assert result is None
        # Adapter's think() should NOT have been called
        adapter.think.assert_not_called()

    async def test_timeout_records_failure(self):
        """When adapter times out, circuit breaker records a failure."""
        import asyncio
        from vecna.orchestrator.loop import CircuitBreaker

        config = HiveConfig()
        loop = HiveLoop(config=config)

        adapter = _make_adapter("slow-adapter", weight=1.0)

        async def slow_think(*args, **kwargs):
            await asyncio.sleep(10)
            return ("response", MagicMock())

        adapter.think = slow_think

        breaker = CircuitBreaker(adapter_name="slow-adapter")
        loop._circuit_breakers = {"slow-adapter": breaker}

        result = await loop._call_adapter_with_timeout(adapter, "test prompt", timeout=0.01)
        assert result is None
        assert breaker.failure_count == 1

    async def test_successful_call_resets_breaker(self):
        """A successful adapter call resets the circuit breaker."""
        from vecna.orchestrator.loop import CircuitBreaker

        config = HiveConfig()
        loop = HiveLoop(config=config)

        adapter = _make_adapter("good-adapter", weight=1.0)
        mock_update = MagicMock()

        async def good_think(*args, **kwargs):
            return ("good response", mock_update)

        adapter.think = good_think

        breaker = CircuitBreaker(adapter_name="good-adapter")
        breaker.record_failure()
        breaker.record_failure()
        loop._circuit_breakers = {"good-adapter": breaker}

        result = await loop._call_adapter_with_timeout(adapter, "test prompt")
        assert result == ("good response", mock_update)
        assert breaker.failure_count == 0

    async def test_adapter_error_records_failure(self):
        """When adapter raises an exception, circuit breaker records a failure."""
        from vecna.orchestrator.loop import CircuitBreaker

        config = HiveConfig()
        loop = HiveLoop(config=config)

        adapter = _make_adapter("error-adapter", weight=1.0)

        async def error_think(*args, **kwargs):
            raise ConnectionError("API unavailable")

        adapter.think = error_think

        breaker = CircuitBreaker(adapter_name="error-adapter")
        loop._circuit_breakers = {"error-adapter": breaker}

        result = await loop._call_adapter_with_timeout(adapter, "test prompt")
        assert result is None
        assert breaker.failure_count == 1

    async def test_unexpected_adapter_exception_records_failure(self):
        """Adapter-specific SDK exceptions are isolated by the wrapper."""
        config = HiveConfig()
        loop = HiveLoop(config=config)

        adapter = _make_adapter("sdk-adapter", weight=1.0)

        class ProviderSDKError(Exception):
            pass

        async def bad_think(*args, **kwargs):
            raise ProviderSDKError("provider exploded")

        adapter.think = bad_think

        result = await loop._call_adapter_with_timeout(adapter, "test prompt")
        assert result is None
        assert loop._circuit_breakers["sdk-adapter"].failure_count == 1

    async def test_breaker_is_created_on_first_call(self):
        """Adapter call path lazily creates a circuit breaker for that adapter."""
        config = HiveConfig()
        loop = HiveLoop(config=config)

        adapter = _make_adapter("new-adapter", weight=1.0)
        mock_update = MagicMock()

        async def good_think(*args, **kwargs):
            return ("ok", mock_update)

        adapter.think = good_think

        assert "new-adapter" not in loop._circuit_breakers
        result = await loop._call_adapter_with_timeout(adapter, "test prompt")

        assert result == ("ok", mock_update)
        assert "new-adapter" in loop._circuit_breakers
        assert loop._circuit_breakers["new-adapter"].failure_count == 0

    async def test_run_cycle_uses_adapter_timeout_setting(self):
        """_run_cycle enforces config.adapter_timeout through adapter call wrapper."""
        import asyncio

        config = HiveConfig(use_routing=False)
        config.adapter_timeout = 0.01
        loop = HiveLoop(config=config)

        adapter = _make_adapter("slow-adapter", weight=1.0)

        async def slow_think(*args, **kwargs):
            await asyncio.sleep(0.1)
            return ("late response", MagicMock())

        adapter.think = slow_think
        loop.adapters = [adapter]

        response_map, updates = await loop._run_cycle("timeout check")

        assert response_map == {}
        assert updates[0].source_model == "slow-adapter"
        assert loop._circuit_breakers["slow-adapter"].failure_count == 1
