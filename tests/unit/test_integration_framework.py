"""
Tests for the integration framework.

Tests:
- BaseIntegration ABC (name, description, enabled toggle, health check, credentials)
- IntegrationRegistry (register, list, get)
- IntegrationConfig (enable, disable, serialization, credentials)
- Error paths (Amendment 10): invalid source, missing credentials, unknown integration
- Concurrency (Amendment 12): concurrent registry/config operations
"""

import asyncio
from typing import List

from vecna.integrations.base import BaseIntegration, IntegrationStatus
from vecna.integrations.config import IntegrationConfig, IntegrationRegistry


class MockIntegration(BaseIntegration):
    """Test integration."""

    name = "mock"
    description = "A mock integration for testing"
    required_credentials = ["mock_api_key"]

    async def check_health(self) -> IntegrationStatus:
        return IntegrationStatus(
            healthy=True,
            name=self.name,
            message="OK",
        )

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False


class FailingIntegration(BaseIntegration):
    """Integration that always fails health checks."""

    name = "failing"
    description = "An integration that always fails"
    required_credentials = ["fail_key", "fail_secret"]

    async def check_health(self) -> IntegrationStatus:
        return IntegrationStatus(
            healthy=False,
            name=self.name,
            message="Connection refused",
        )

    async def start(self) -> None:
        raise ConnectionError("Cannot connect to failing service")

    async def stop(self) -> None:
        pass


class TestIntegrationBase:
    """Tests for BaseIntegration ABC."""

    def test_integration_has_name(self):
        integration = MockIntegration()
        assert integration.name == "mock"

    def test_integration_has_description(self):
        integration = MockIntegration()
        assert integration.description == "A mock integration for testing"

    def test_integration_disabled_by_default(self):
        integration = MockIntegration()
        assert integration.enabled is False

    def test_integration_enable_toggle(self):
        integration = MockIntegration()
        integration.enabled = True
        assert integration.enabled is True

    def test_integration_disable_after_enable(self):
        integration = MockIntegration()
        integration.enabled = True
        integration.enabled = False
        assert integration.enabled is False

    async def test_health_check_returns_status(self):
        integration = MockIntegration()
        status = await integration.check_health()
        assert status.healthy is True
        assert status.name == "mock"
        assert status.message == "OK"

    async def test_unhealthy_check(self):
        integration = FailingIntegration()
        status = await integration.check_health()
        assert status.healthy is False
        assert status.name == "failing"
        assert status.message == "Connection refused"

    def test_required_credentials(self):
        integration = MockIntegration()
        assert integration.required_credentials == ["mock_api_key"]

    def test_get_credential_keys(self):
        integration = MockIntegration()
        keys = integration.get_credential_keys()
        assert keys == ["mock_api_key"]

    def test_multiple_required_credentials(self):
        integration = FailingIntegration()
        assert integration.required_credentials == ["fail_key", "fail_secret"]

    async def test_start_and_stop(self):
        integration = MockIntegration()
        await integration.start()
        await integration.stop()

    async def test_start_failure_propagates(self):
        """Error path: start() raises specific exception on connection failure."""
        integration = FailingIntegration()
        try:
            await integration.start()
            assert False, "Expected ConnectionError"
        except ConnectionError as e:
            assert "Cannot connect to failing service" in str(e)


class TestIntegrationStatus:
    """Tests for IntegrationStatus dataclass."""

    def test_status_fields(self):
        status = IntegrationStatus(
            healthy=True,
            name="test",
            message="All good",
        )
        assert status.healthy is True
        assert status.name == "test"
        assert status.message == "All good"

    def test_status_default_metadata(self):
        status = IntegrationStatus(healthy=True, name="test", message="ok")
        assert status.metadata == {}

    def test_status_with_metadata(self):
        status = IntegrationStatus(
            healthy=True,
            name="test",
            message="ok",
            metadata={"version": "1.0", "latency_ms": 42},
        )
        assert status.metadata["version"] == "1.0"
        assert status.metadata["latency_ms"] == 42

    def test_status_last_checked_is_set(self):
        status = IntegrationStatus(healthy=True, name="test", message="ok")
        assert status.last_checked is not None
        # Verify it's a datetime, not just truthy
        assert status.last_checked.year >= 2024


class TestIntegrationRegistry:
    """Tests for IntegrationRegistry."""

    def test_register_integration(self):
        registry = IntegrationRegistry()
        registry.register(MockIntegration)
        assert "mock" in registry.list_available()

    def test_register_multiple_integrations(self):
        registry = IntegrationRegistry()
        registry.register(MockIntegration)
        registry.register(FailingIntegration)
        available = registry.list_available()
        assert "mock" in available
        assert "failing" in available

    def test_get_registered_integration(self):
        registry = IntegrationRegistry()
        registry.register(MockIntegration)
        cls = registry.get("mock")
        assert cls is MockIntegration

    def test_get_unregistered_integration_raises_keyerror(self):
        """Error path: accessing non-existent integration raises KeyError."""
        registry = IntegrationRegistry()
        try:
            registry.get("nonexistent")
            assert False, "Expected KeyError"
        except KeyError as e:
            assert "nonexistent" in str(e)

    def test_list_empty_registry(self):
        registry = IntegrationRegistry()
        assert registry.list_available() == []

    def test_register_replaces_existing(self):
        """Registering the same name replaces the previous class."""
        registry = IntegrationRegistry()
        registry.register(MockIntegration)

        class AnotherMock(BaseIntegration):
            name = "mock"
            description = "replacement"
            required_credentials: List[str] = []

            async def check_health(self) -> IntegrationStatus:
                return IntegrationStatus(healthy=True, name="mock", message="v2")

            async def start(self) -> None:
                pass

            async def stop(self) -> None:
                pass

        registry.register(AnotherMock)
        assert registry.get("mock") is AnotherMock

    def test_instantiate_from_registry(self):
        """Can get a class from registry and instantiate it."""
        registry = IntegrationRegistry()
        registry.register(MockIntegration)
        cls = registry.get("mock")
        instance = cls()
        assert instance.name == "mock"
        assert instance.description == "A mock integration for testing"


class TestIntegrationConfig:
    """Tests for IntegrationConfig."""

    def test_enable_integration(self):
        config = IntegrationConfig()
        config.enable("mock")
        assert config.is_enabled("mock") is True

    def test_disable_integration(self):
        config = IntegrationConfig()
        config.enable("mock")
        config.disable("mock")
        assert config.is_enabled("mock") is False

    def test_is_enabled_returns_false_for_unknown(self):
        config = IntegrationConfig()
        assert config.is_enabled("nonexistent") is False

    def test_disable_already_disabled_is_noop(self):
        config = IntegrationConfig()
        config.disable("mock")  # Should not raise
        assert config.is_enabled("mock") is False

    def test_enable_idempotent(self):
        config = IntegrationConfig()
        config.enable("mock")
        config.enable("mock")
        assert config.is_enabled("mock") is True

    def test_multiple_integrations(self):
        config = IntegrationConfig()
        config.enable("mock")
        config.enable("github")
        config.enable("slack")
        assert config.is_enabled("mock") is True
        assert config.is_enabled("github") is True
        assert config.is_enabled("slack") is True
        config.disable("github")
        assert config.is_enabled("github") is False
        assert config.is_enabled("mock") is True

    def test_serialization_roundtrip(self):
        config = IntegrationConfig()
        config.enable("mock")
        config.enable("github")
        d = config.to_dict()
        restored = IntegrationConfig.from_dict(d)
        assert restored.is_enabled("mock") is True
        assert restored.is_enabled("github") is True
        assert restored.is_enabled("nonexistent") is False

    def test_serialization_excludes_credentials(self):
        """Credentials must never appear in serialized output."""
        config = IntegrationConfig()
        config.enable("mock")
        config.set_credentials("mock", {"mock_api_key": "secret-123"})
        d = config.to_dict()
        assert "secret-123" not in str(d)
        assert d["credentials"] == {}

    def test_set_and_get_credentials(self):
        config = IntegrationConfig()
        config.set_credentials("mock", {"mock_api_key": "abc123"})
        creds = config.get_credentials("mock")
        assert creds["mock_api_key"] == "abc123"

    def test_get_credentials_returns_empty_for_unknown(self):
        config = IntegrationConfig()
        assert config.get_credentials("nonexistent") == {}

    def test_from_dict_with_empty_data(self):
        config = IntegrationConfig.from_dict({})
        assert config.is_enabled("anything") is False

    def test_list_enabled(self):
        config = IntegrationConfig()
        config.enable("mock")
        config.enable("github")
        enabled = config.list_enabled()
        assert sorted(enabled) == ["github", "mock"]


class TestIntegrationErrorPaths:
    """Error and edge-case tests (Amendment 10)."""

    def test_registry_get_unknown_integration_raises_keyerror(self):
        """Unknown integration name must raise KeyError with the name in the message."""
        registry = IntegrationRegistry()
        registry.register(MockIntegration)
        try:
            registry.get("unknown_source")
            assert False, "Expected KeyError for unknown integration"
        except KeyError as e:
            assert "unknown_source" in str(e)

    def test_config_validate_credentials_missing_required(self):
        """Missing required credentials must produce a clear error listing what's missing."""
        registry = IntegrationRegistry()
        registry.register(MockIntegration)
        config = IntegrationConfig()
        config.enable("mock")
        # Provide empty credentials — validation should catch it
        config.set_credentials("mock", {})
        missing = config.validate_credentials("mock", registry)
        assert "mock_api_key" in missing

    def test_config_validate_credentials_partial(self):
        """Partial credentials should list only the missing ones."""
        registry = IntegrationRegistry()
        registry.register(FailingIntegration)
        config = IntegrationConfig()
        config.enable("failing")
        config.set_credentials("failing", {"fail_key": "present"})
        missing = config.validate_credentials("failing", registry)
        assert "fail_secret" in missing
        assert "fail_key" not in missing

    def test_config_validate_credentials_all_present(self):
        """When all required credentials are present, validation returns empty list."""
        registry = IntegrationRegistry()
        registry.register(MockIntegration)
        config = IntegrationConfig()
        config.enable("mock")
        config.set_credentials("mock", {"mock_api_key": "value"})
        missing = config.validate_credentials("mock", registry)
        assert missing == []

    def test_config_validate_credentials_unregistered_raises(self):
        """Validating credentials for unregistered integration raises KeyError."""
        registry = IntegrationRegistry()
        config = IntegrationConfig()
        try:
            config.validate_credentials("unregistered", registry)
            assert False, "Expected KeyError"
        except KeyError as e:
            assert "unregistered" in str(e)


class TestIntegrationConcurrency:
    """Concurrency tests (Amendment 12)."""

    async def test_concurrent_registry_register(self):
        """50+ concurrent register operations should not lose any registrations."""
        registry = IntegrationRegistry()

        async def register_one(index: int) -> None:
            # Dynamically create integration classes with unique names
            cls = type(
                f"Integration{index}",
                (MockIntegration,),
                {"name": f"integration_{index}"},
            )
            registry.register(cls)

        await asyncio.gather(*(register_one(i) for i in range(50)))
        available = registry.list_available()
        # All 50 should be present
        for i in range(50):
            assert f"integration_{i}" in available, f"integration_{i} missing from registry"

    async def test_concurrent_config_enable_disable(self):
        """50+ concurrent enable/disable operations should not corrupt state."""
        config = IntegrationConfig()

        async def toggle(index: int) -> None:
            name = f"int_{index}"
            config.enable(name)
            # Small yield to allow interleaving
            await asyncio.sleep(0)
            if index % 2 == 0:
                config.disable(name)

        await asyncio.gather(*(toggle(i) for i in range(50)))
        # Even indices should be disabled, odd should be enabled
        for i in range(50):
            name = f"int_{i}"
            if i % 2 == 0:
                assert config.is_enabled(name) is False, f"{name} should be disabled"
            else:
                assert config.is_enabled(name) is True, f"{name} should be enabled"
