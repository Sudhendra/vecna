"""
Composio integration bridge for Slack, Discord, and GitHub.

Bridges Composio's pre-built integration actions into Vecna's ToolRegistry.
Composio provides 100+ integrations via function calling — we convert their
tool schemas into ToolSpec objects and route execution through Vecna's
ToolRuntime (permissions, quotas, audit).

Optional dependency: ``pip install composio-core``
Falls back to stub executors when Composio is not installed.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from vecna.tools.types import ToolExecutionContext, ToolResult, ToolSpec

logger = logging.getLogger("vecna.integrations.composio_bridge")


# -- Default actions we support --
COMPOSIO_DEFAULT_ACTIONS: Dict[str, Dict[str, Any]] = {
    "slack_send_message": {
        "description": "Send a message to a Slack channel",
        "input_schema": {"channel": "string", "message": "string"},
        "app": "slack",
    },
    "slack_read_channel": {
        "description": "Read recent messages from a Slack channel",
        "input_schema": {"channel": "string", "limit": "int"},
        "app": "slack",
    },
    "github_list_prs": {
        "description": "List open pull requests for a GitHub repository",
        "input_schema": {"repo": "string", "state": "string"},
        "app": "github",
    },
    "github_create_issue": {
        "description": "Create a new issue on a GitHub repository",
        "input_schema": {"repo": "string", "title": "string", "body": "string"},
        "app": "github",
    },
    "discord_send_message": {
        "description": "Send a message to a Discord channel",
        "input_schema": {"channel_id": "string", "message": "string"},
        "app": "discord",
    },
}


@dataclass
class ComposioConfig:
    """Configuration for the Composio bridge."""

    api_key: Optional[str] = None
    enabled_apps: List[str] = field(default_factory=list)
    max_actions_per_app: int = 10


@dataclass
class ComposioToolAdapter:
    """Adapter that converts a Composio action into a Vecna ToolSpec."""

    action_name: str
    description: str
    input_schema: Dict[str, Any]
    app_name: str

    def to_tool_spec(self) -> ToolSpec:
        """Convert this action to a Vecna ToolSpec."""
        return ToolSpec(
            name=f"composio_{self.action_name}",
            description=self.description,
            input_schema=self.input_schema,
            tags=["composio", self.app_name, "integration"],
        )


class ComposioBridge:
    """
    Bridge between Composio's integration SDK and Vecna's ToolRegistry.

    Converts Composio action schemas to ToolSpec objects and wraps
    their execution through Vecna's tool runtime.

    When Composio is not installed, provides stub executors that
    return informative error messages.

    Parameters
    ----------
    config : ComposioConfig, optional
        Bridge configuration (API key, enabled apps, etc.).
    use_stubs : bool
        If True, skip SDK initialization and use stub executors only.
    composio_client : object, optional
        Pre-initialized Composio client (for testing / dependency injection).
    """

    def __init__(
        self,
        config: Optional[ComposioConfig] = None,
        use_stubs: bool = False,
        composio_client: Optional[Any] = None,
    ) -> None:
        self._config = config or ComposioConfig()
        self._use_stubs = use_stubs
        self._composio_client: Optional[Any] = composio_client
        self._is_available = composio_client is not None

        # Try to import and initialize Composio SDK (only when not using stubs
        # and no client was injected)
        if not use_stubs and not composio_client and self._config.api_key:
            try:
                from composio import Composio  # type: ignore[import-untyped]

                self._composio_client = Composio(api_key=self._config.api_key)
                self._is_available = True
                logger.info("Composio SDK loaded successfully")
            except ImportError:
                logger.warning(
                    "Composio SDK not installed. Install with: pip install composio-core"
                )
            except (RuntimeError, ConnectionError) as e:
                logger.error("Failed to initialize Composio: %s", e)

    # -- Public properties --

    @property
    def is_available(self) -> bool:
        """Whether the Composio SDK is loaded and configured."""
        return self._is_available

    @property
    def config(self) -> ComposioConfig:
        """Return the bridge configuration."""
        return self._config

    # -- Action discovery --

    def list_available_actions(self) -> List[ComposioToolAdapter]:
        """List all available Composio actions.

        If the SDK is available, loads actions from it (falling back to
        defaults on error). Otherwise returns the built-in defaults.
        """
        if self._is_available and self._composio_client:
            return self.load_actions_from_sdk()
        return self._load_default_actions()

    def _load_default_actions(self) -> List[ComposioToolAdapter]:
        """Load the built-in default action definitions."""
        adapters: List[ComposioToolAdapter] = []
        for name, definition in COMPOSIO_DEFAULT_ACTIONS.items():
            adapters.append(
                ComposioToolAdapter(
                    action_name=name,
                    description=definition["description"],
                    input_schema=definition["input_schema"],
                    app_name=definition["app"],
                )
            )
        return adapters

    def load_actions_from_sdk(self) -> List[ComposioToolAdapter]:
        """Load actions from the Composio SDK.

        Falls back to default actions on error.
        """
        if not self._composio_client:
            return self._load_default_actions()

        adapters: List[ComposioToolAdapter] = []
        try:
            actions = self._composio_client.get_actions()
            for action in actions:
                name = action.get("name", "")
                if not name:
                    continue

                # Convert Composio parameter schema to our flat format
                params = action.get("parameters", {})
                input_schema: Dict[str, Any] = {}
                for param_name, param_def in params.items():
                    input_schema[param_name] = param_def.get("type", "string")

                adapters.append(
                    ComposioToolAdapter(
                        action_name=name,
                        description=action.get("description", ""),
                        input_schema=input_schema,
                        app_name=action.get("app", "unknown"),
                    )
                )
        except (RuntimeError, ConnectionError) as e:
            logger.error("Failed to load actions from Composio SDK: %s", e)
            return self._load_default_actions()

        return adapters or self._load_default_actions()

    # -- Tool registration --

    def register_tools(self, registry: Any) -> int:
        """Register all available Composio actions into a ToolRegistry.

        Returns the number of tools registered.
        """
        actions = self.list_available_actions()
        registered = 0

        for adapter in actions:
            spec = adapter.to_tool_spec()

            if self._is_available and self._composio_client:
                executor = self.create_sdk_executor(adapter.action_name)
            else:
                executor = self.create_stub_executor(adapter.action_name)

            try:
                registry.register(spec, executor)
                registered += 1
            except ValueError:
                # Tool already registered — skip silently
                logger.debug("Tool %s already registered, skipping", spec.name)

        logger.info("Registered %d Composio tools", registered)
        return registered

    # -- Executor factories --

    def create_stub_executor(
        self, action_name: str
    ) -> Callable[[Dict[str, Any], ToolExecutionContext], ToolResult]:
        """Create a stub executor that returns a 'not configured' error."""

        def stub_executor(args: Dict[str, Any], ctx: ToolExecutionContext) -> ToolResult:
            return ToolResult(
                tool_name=f"composio_{action_name}",
                success=False,
                output="",
                error=(
                    f"Composio action '{action_name}' is not configured. "
                    f"Set COMPOSIO_API_KEY and install composio-core to enable."
                ),
            )

        return stub_executor

    def create_sdk_executor(
        self, action_name: str
    ) -> Callable[[Dict[str, Any], ToolExecutionContext], ToolResult]:
        """Create an executor that delegates to the Composio SDK."""
        client = self._composio_client

        def sdk_executor(args: Dict[str, Any], ctx: ToolExecutionContext) -> ToolResult:
            try:
                result = client.execute_action(action_name, params=args)

                if isinstance(result, dict):
                    success = result.get("success", True)
                    data = result.get("data", result)
                    output = str(data)
                else:
                    success = True
                    output = str(result)

                return ToolResult(
                    tool_name=f"composio_{action_name}",
                    success=success,
                    output=output,
                    metadata={"action": action_name, "args": args},
                )
            except (RuntimeError, ConnectionError) as e:
                logger.error("Composio action '%s' failed: %s", action_name, e)
                return ToolResult(
                    tool_name=f"composio_{action_name}",
                    success=False,
                    output="",
                    error=str(e),
                )

        return sdk_executor
