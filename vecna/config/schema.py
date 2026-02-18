"""
Vecna Configuration Schema

Defines the structure for personas, models, groups, memory, and runtime settings.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
from typing import Any, Dict, List, Optional

from vecna.tools.permissions import RiskTier, ToolPolicy


logger = logging.getLogger("vecna.config")


class Provider(str, Enum):
    """Supported model providers."""

    COPILOT = "copilot"  # Primary - GitHub Copilot API
    OLLAMA = "ollama"  # Local models via Ollama
    TRANSFORMERS = "transformers"  # Local HuggingFace models
    GROQ = "groq"  # Groq fast inference (optional)
    OPENAI = "openai"  # Native OpenAI API
    ANTHROPIC = "anthropic"  # Native Anthropic API


class StorageBackend(str, Enum):
    """Supported storage backends. PostgreSQL + Redis is the only supported backend."""

    POSTGRES = "postgres"


class AgentMode(str, Enum):
    """Agent autonomy mode."""

    assistant = "assistant"
    explorer = "explorer"


@dataclass
class MemoryConfig:
    """
    Configuration for Vecna's memory substrate.

    Defines connection strings and settings for:
    - PostgreSQL (warm storage)
    - Redis (hot cache)
    - Embedding generation
    """

    # Storage backend selection (PostgreSQL only)
    backend: StorageBackend = StorageBackend.POSTGRES

    # PostgreSQL settings
    pg_url: Optional[str] = None  # Connection string, or use VECNA_PG_URL env var
    pg_pool_size: int = 5
    pg_max_overflow: int = 10

    # Redis settings (hot cache)
    redis_url: Optional[str] = None  # Connection string, or use VECNA_REDIS_URL env var
    redis_max_events: int = 1000  # Max events in hot cache ring buffer
    redis_event_ttl: int = 3600  # Event TTL in seconds (1 hour)
    redis_embed_ttl: int = 86400  # Embedding cache TTL in seconds (24 hours)

    # Embedding settings
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    cache_embeddings: bool = True  # Cache embeddings in Redis to reduce API costs

    # Memory retrieval settings
    default_top_k: int = 10
    default_min_confidence: float = 0.3
    max_context_chars: int = 4000

    # Hybrid search weighting
    vector_weight: float = 0.7
    text_weight: float = 0.3

    # Compaction thresholds
    flush_token_threshold: int = 6000

    # Markdown indexing
    markdown_chunk_tokens: int = 400

    # Dream loop settings
    dream_enabled: bool = False
    dream_interval_hours: int = 24
    dream_compress_after_days: int = 7

    # Dataset export settings
    export_format: str = "jsonl"  # jsonl or parquet
    export_path: Optional[str] = None  # Default: ~/.vecna/exports/

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend": self.backend.value
            if isinstance(self.backend, StorageBackend)
            else self.backend,
            "pg_url": self.pg_url,
            "pg_pool_size": self.pg_pool_size,
            "pg_max_overflow": self.pg_max_overflow,
            "redis_url": self.redis_url,
            "redis_max_events": self.redis_max_events,
            "redis_event_ttl": self.redis_event_ttl,
            "redis_embed_ttl": self.redis_embed_ttl,
            "embedding_model": self.embedding_model,
            "embedding_dim": self.embedding_dim,
            "cache_embeddings": self.cache_embeddings,
            "default_top_k": self.default_top_k,
            "default_min_confidence": self.default_min_confidence,
            "max_context_chars": self.max_context_chars,
            "vector_weight": self.vector_weight,
            "text_weight": self.text_weight,
            "flush_token_threshold": self.flush_token_threshold,
            "markdown_chunk_tokens": self.markdown_chunk_tokens,
            "dream_enabled": self.dream_enabled,
            "dream_interval_hours": self.dream_interval_hours,
            "dream_compress_after_days": self.dream_compress_after_days,
            "export_format": self.export_format,
            "export_path": self.export_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryConfig":
        backend = data.get("backend", "postgres")
        if isinstance(backend, str):
            try:
                backend = StorageBackend(backend)
            except ValueError:
                # Default to POSTGRES for any invalid/legacy value
                backend = StorageBackend.POSTGRES

        return cls(
            backend=backend,
            pg_url=data.get("pg_url"),
            pg_pool_size=data.get("pg_pool_size", 5),
            pg_max_overflow=data.get("pg_max_overflow", 10),
            redis_url=data.get("redis_url"),
            redis_max_events=data.get("redis_max_events", 1000),
            redis_event_ttl=data.get("redis_event_ttl", 3600),
            redis_embed_ttl=data.get("redis_embed_ttl", 86400),
            embedding_model=data.get("embedding_model", "text-embedding-3-small"),
            embedding_dim=data.get("embedding_dim", 1536),
            cache_embeddings=data.get("cache_embeddings", True),
            default_top_k=data.get("default_top_k", 10),
            default_min_confidence=data.get("default_min_confidence", 0.3),
            max_context_chars=data.get("max_context_chars", 4000),
            vector_weight=data.get("vector_weight", 0.7),
            text_weight=data.get("text_weight", 0.3),
            flush_token_threshold=data.get("flush_token_threshold", 6000),
            markdown_chunk_tokens=data.get("markdown_chunk_tokens", 400),
            dream_enabled=data.get("dream_enabled", False),
            dream_interval_hours=data.get("dream_interval_hours", 24),
            dream_compress_after_days=data.get("dream_compress_after_days", 7),
            export_format=data.get("export_format", "jsonl"),
            export_path=data.get("export_path"),
        )


@dataclass
class PersonaConfig:
    """
    A persona defines a style/tone overlay for the hive mind.

    Personas affect HOW Vecna communicates, not WHO Vecna is.
    The core identity (axioms, memory, self-model) remains unchanged.
    """

    name: str
    description: str  # Internal description for reference
    prompt: str  # The actual prompt text injected into system message

    # Optional: tone hints for the self-model
    tone_hint: Optional[str] = None  # e.g., "analytical", "creative", "terse"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "prompt": self.prompt,
            "tone_hint": self.tone_hint,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PersonaConfig":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            prompt=data["prompt"],
            tone_hint=data.get("tone_hint"),
        )


@dataclass
class ModelEntry:
    """
    Configuration for a single model in the hive.

    Consistent schema across all providers.
    """

    name: str  # Unique friendly name (e.g., "gpt5", "claude-sonnet")
    provider: Provider  # Which provider/adapter to use
    model_id: str  # Provider-specific model identifier
    domain: str = "general"  # Routing domain: general, code, math, creative, etc.
    weight: float = 1.0  # Influence weight in consensus (0.0 - 2.0)
    temperature: float = 0.7  # Generation temperature
    max_tokens: int = 4096  # Max output tokens
    persona_override: Optional[str] = None  # Override default persona for this model
    enabled: bool = True  # Whether to include in hive

    # Provider-specific settings
    api_key_env: Optional[str] = None  # Env var name for API key (e.g., "OPENAI_API_KEY")
    base_url: Optional[str] = None  # Custom base URL (for Ollama, etc.)
    extra_params: Dict[str, Any] = field(default_factory=dict)  # Provider-specific params

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "provider": self.provider.value
            if isinstance(self.provider, Provider)
            else self.provider,
            "model_id": self.model_id,
            "domain": self.domain,
            "weight": self.weight,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "persona_override": self.persona_override,
            "enabled": self.enabled,
            "api_key_env": self.api_key_env,
            "base_url": self.base_url,
            "extra_params": self.extra_params,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelEntry":
        provider = data.get("provider", "copilot")
        if isinstance(provider, str):
            try:
                provider = Provider(provider)
            except ValueError:
                provider = Provider.COPILOT

        return cls(
            name=data["name"],
            provider=provider,
            model_id=data["model_id"],
            domain=data.get("domain", "general"),
            weight=data.get("weight", 1.0),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 4096),
            persona_override=data.get("persona_override"),
            enabled=data.get("enabled", True),
            api_key_env=data.get("api_key_env"),
            base_url=data.get("base_url"),
            extra_params=data.get("extra_params", {}),
        )


@dataclass
class GroupConfig:
    """
    A group is a preset combination of models and persona.

    Switch groups to change the active model set and default persona.
    Examples: "default", "creative", "code-review", "research"
    """

    name: str
    description: str
    models: List[str]  # List of model names to activate
    persona: str  # Default persona for this group
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "models": self.models,
            "persona": self.persona,
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GroupConfig":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            models=data.get("models", []),
            persona=data.get("persona", "concise"),
            enabled=data.get("enabled", True),
        )


@dataclass
class ToolPolicyConfig:
    default_action: str = "deny"
    allowlist: List[str] = field(default_factory=list)
    denylist: List[str] = field(default_factory=list)
    risk_actions: Dict[str, str] = field(
        default_factory=lambda: {
            "low": "allow",
            "medium": "ask",
            "high": "deny",
            "critical": "deny",
        }
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "default_action": self.default_action,
            "allowlist": list(self.allowlist),
            "denylist": list(self.denylist),
            "risk_actions": dict(self.risk_actions),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolPolicyConfig":
        return cls(
            default_action=data.get("default_action", "deny"),
            allowlist=data.get("allowlist", []) or [],
            denylist=data.get("denylist", []) or [],
            risk_actions=data.get(
                "risk_actions",
                {
                    "low": "allow",
                    "medium": "ask",
                    "high": "deny",
                    "critical": "deny",
                },
            ),
        )

    def to_policy(self) -> ToolPolicy:
        return ToolPolicy(
            default_action=self.default_action,
            allowlist=list(self.allowlist),
            denylist=list(self.denylist),
            risk_actions={RiskTier(key): value for key, value in (self.risk_actions or {}).items()},
        )


@dataclass
class VecnaConfig:
    """
    Root configuration object for Vecna.

    Stored in ~/.vecna/config.json
    """

    # Persona definitions
    personas: Dict[str, PersonaConfig] = field(default_factory=dict)

    # Model definitions
    models: Dict[str, ModelEntry] = field(default_factory=dict)

    # Group definitions
    groups: Dict[str, GroupConfig] = field(default_factory=dict)

    # Runtime defaults
    active_group: str = "default"
    active_persona: str = "concise"
    workspace_dir: str = "~/.vecna"

    # Memory substrate settings
    memory: MemoryConfig = field(default_factory=MemoryConfig)

    # Hive settings
    max_parallel_models: int = 5
    use_routing: bool = True  # Route by domain or use all models
    auto_execute_code: bool = True  # Execute Python code blocks in responses
    auto_execute_tools: bool = True
    tool_policy: ToolPolicyConfig = field(default_factory=ToolPolicyConfig)

    # Agent autonomy settings
    agent_mode: AgentMode = AgentMode.assistant
    enable_autonomy_heartbeat: bool = False
    heartbeat_interval_seconds: int = 900
    heartbeat_jitter_seconds: int = 90

    # ReWOO planning settings
    enable_rewoo_planning: bool = False
    rewoo_max_steps: int = 8
    rewoo_retry_limit: int = 1
    rewoo_backoff_base_seconds: float = 0.25
    rewoo_max_artifact_chars: int = 4000
    rewoo_policy_denied_behavior: str = "fail_step"
    rewoo_artifact_injection_mode: str = "final_summary"
    rewoo_use_separate_synthesizer: bool = False
    rewoo_min_task_words: int = 8
    rewoo_force: bool = False

    # Tooling feature flags and quotas
    enable_web_tools: bool = False
    enable_fs_tools: bool = False
    tool_quota_per_session: int = 0
    tool_quota_per_tool: int = 0
    tool_allowed_fs_roots: List[str] = field(default_factory=lambda: ["~/.vecna"])

    # Version for schema migrations
    config_version: int = 2

    def get_active_persona(self) -> Optional[PersonaConfig]:
        """Get the currently active persona config."""
        return self.personas.get(self.active_persona)

    def get_active_group(self) -> Optional[GroupConfig]:
        """Get the currently active group config."""
        return self.groups.get(self.active_group)

    def get_active_models(self) -> List[ModelEntry]:
        """Get list of models that should be active based on current group."""
        group = self.get_active_group()
        if not group:
            # No group, return all enabled models
            return [m for m in self.models.values() if m.enabled]

        # Return models in the group that exist and are enabled
        return [
            self.models[name]
            for name in group.models
            if name in self.models and self.models[name].enabled
        ]

    def get_model_persona(self, model_name: str) -> Optional[PersonaConfig]:
        """Get the effective persona for a specific model."""
        model = self.models.get(model_name)
        if model and model.persona_override:
            return self.personas.get(model.persona_override)
        return self.get_active_persona()

    @staticmethod
    def _normalize_tool_allowed_fs_roots(value: Any) -> List[str]:
        if isinstance(value, str):
            return [value]

        if isinstance(value, list):
            normalized = [item for item in value if isinstance(item, str)]
            return normalized or ["~/.vecna"]

        return ["~/.vecna"]

    def to_dict(self) -> Dict[str, Any]:
        agent_mode = self.agent_mode
        if isinstance(agent_mode, str):
            try:
                agent_mode = AgentMode(agent_mode)
            except ValueError:
                logger.warning(
                    "Invalid agent_mode '%s' in config; defaulting to 'assistant'",
                    agent_mode,
                )
                agent_mode = AgentMode.assistant
        elif not isinstance(agent_mode, AgentMode):
            logger.warning(
                "Invalid agent_mode '%s' in config; defaulting to 'assistant'",
                agent_mode,
            )
            agent_mode = AgentMode.assistant

        return {
            "config_version": self.config_version,
            "personas": {k: v.to_dict() for k, v in self.personas.items()},
            "models": {k: v.to_dict() for k, v in self.models.items()},
            "groups": {k: v.to_dict() for k, v in self.groups.items()},
            "memory": self.memory.to_dict(),
            "active_group": self.active_group,
            "active_persona": self.active_persona,
            "workspace_dir": self.workspace_dir,
            "max_parallel_models": self.max_parallel_models,
            "use_routing": self.use_routing,
            "auto_execute_code": self.auto_execute_code,
            "agent_mode": agent_mode.value,
            "enable_autonomy_heartbeat": self.enable_autonomy_heartbeat,
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "heartbeat_jitter_seconds": self.heartbeat_jitter_seconds,
            "auto_execute_tools": self.auto_execute_tools,
            "tool_policy": self.tool_policy.to_dict(),
            "enable_rewoo_planning": self.enable_rewoo_planning,
            "rewoo_max_steps": self.rewoo_max_steps,
            "rewoo_retry_limit": self.rewoo_retry_limit,
            "rewoo_backoff_base_seconds": self.rewoo_backoff_base_seconds,
            "rewoo_max_artifact_chars": self.rewoo_max_artifact_chars,
            "rewoo_policy_denied_behavior": self.rewoo_policy_denied_behavior,
            "rewoo_artifact_injection_mode": self.rewoo_artifact_injection_mode,
            "rewoo_use_separate_synthesizer": self.rewoo_use_separate_synthesizer,
            "rewoo_min_task_words": self.rewoo_min_task_words,
            "rewoo_force": self.rewoo_force,
            "enable_web_tools": self.enable_web_tools,
            "enable_fs_tools": self.enable_fs_tools,
            "tool_quota_per_session": self.tool_quota_per_session,
            "tool_quota_per_tool": self.tool_quota_per_tool,
            "tool_allowed_fs_roots": self._normalize_tool_allowed_fs_roots(
                self.tool_allowed_fs_roots
            ),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VecnaConfig":
        personas = {}
        for k, v in data.get("personas", {}).items():
            if isinstance(v, str):
                # Legacy format: just prompt string
                personas[k] = PersonaConfig(name=k, description="", prompt=v)
            else:
                personas[k] = PersonaConfig.from_dict({**v, "name": k})

        models = {}
        for k, v in data.get("models", {}).items():
            models[k] = ModelEntry.from_dict({**v, "name": k})

        groups = {}
        for k, v in data.get("groups", {}).items():
            groups[k] = GroupConfig.from_dict({**v, "name": k})

        # Parse memory config
        memory_data = data.get("memory", {})
        memory = MemoryConfig.from_dict(memory_data) if memory_data else MemoryConfig()

        agent_mode = data.get("agent_mode", AgentMode.assistant)
        if isinstance(agent_mode, str):
            try:
                agent_mode = AgentMode(agent_mode)
            except ValueError:
                logger.warning(
                    "Invalid agent_mode '%s' in config; defaulting to 'assistant'",
                    agent_mode,
                )
                agent_mode = AgentMode.assistant
        elif not isinstance(agent_mode, AgentMode):
            logger.warning(
                "Invalid agent_mode '%s' in config; defaulting to 'assistant'",
                agent_mode,
            )
            agent_mode = AgentMode.assistant
        tool_policy_data = data.get("tool_policy")
        tool_policy = (
            ToolPolicyConfig.from_dict(tool_policy_data)
            if isinstance(tool_policy_data, dict)
            else ToolPolicyConfig()
        )

        auto_execute_tools = data.get("auto_execute_tools")
        if auto_execute_tools is None:
            auto_execute_tools = data.get("auto_execute_code", True)

        return cls(
            personas=personas,
            models=models,
            groups=groups,
            memory=memory,
            active_group=data.get("active_group", "default"),
            active_persona=data.get("active_persona", "concise"),
            workspace_dir=data.get("workspace_dir", "~/.vecna"),
            max_parallel_models=data.get("max_parallel_models", 5),
            use_routing=data.get("use_routing", True),
            auto_execute_code=data.get("auto_execute_code", True),
            agent_mode=agent_mode,
            enable_autonomy_heartbeat=data.get("enable_autonomy_heartbeat", False),
            heartbeat_interval_seconds=data.get("heartbeat_interval_seconds", 900),
            heartbeat_jitter_seconds=data.get("heartbeat_jitter_seconds", 90),
            auto_execute_tools=auto_execute_tools,
            tool_policy=tool_policy,
            enable_rewoo_planning=data.get("enable_rewoo_planning", False),
            rewoo_max_steps=data.get("rewoo_max_steps", 8),
            rewoo_retry_limit=data.get("rewoo_retry_limit", 1),
            rewoo_backoff_base_seconds=data.get("rewoo_backoff_base_seconds", 0.25),
            rewoo_max_artifact_chars=data.get("rewoo_max_artifact_chars", 4000),
            rewoo_policy_denied_behavior=data.get("rewoo_policy_denied_behavior", "fail_step"),
            rewoo_artifact_injection_mode=data.get(
                "rewoo_artifact_injection_mode", "final_summary"
            ),
            rewoo_use_separate_synthesizer=data.get("rewoo_use_separate_synthesizer", False),
            rewoo_min_task_words=data.get("rewoo_min_task_words", 8),
            rewoo_force=data.get("rewoo_force", False),
            enable_web_tools=data.get("enable_web_tools", False),
            enable_fs_tools=data.get("enable_fs_tools", False),
            tool_quota_per_session=data.get("tool_quota_per_session", 0),
            tool_quota_per_tool=data.get("tool_quota_per_tool", 0),
            tool_allowed_fs_roots=cls._normalize_tool_allowed_fs_roots(
                data.get("tool_allowed_fs_roots", ["~/.vecna"])
            ),
            config_version=data.get("config_version", 1),
        )


# ============================================================
# DEFAULT CONFIGURATION
# ============================================================


def get_default_personas() -> Dict[str, PersonaConfig]:
    """Return default persona configurations."""
    return {
        "concise": PersonaConfig(
            name="concise",
            description="Precise, terse responses. Minimal fluff.",
            prompt="Respond with precision and brevity. Be direct. Avoid unnecessary elaboration.",
            tone_hint="analytical",
        ),
        "mentor": PersonaConfig(
            name="mentor",
            description="Patient, thorough teacher. Explains concepts deeply.",
            prompt="You are a patient and thorough teacher. Explain concepts clearly with examples. Guide the user to understanding rather than just giving answers. Ask clarifying questions when appropriate.",
            tone_hint="supportive",
        ),
        "creative": PersonaConfig(
            name="creative",
            description="Divergent thinker. Novel ideas and unconventional approaches.",
            prompt="Think divergently. Propose novel, unconventional ideas. Challenge assumptions. Explore multiple perspectives and possibilities.",
            tone_hint="creative",
        ),
        "analyst": PersonaConfig(
            name="analyst",
            description="Deep analytical thinking. Systematic breakdown of problems.",
            prompt="Analyze systematically. Break down problems into components. Consider edge cases. Evaluate trade-offs explicitly.",
            tone_hint="analytical",
        ),
        "coder": PersonaConfig(
            name="coder",
            description="Code-focused responses. Implementation details matter.",
            prompt="Focus on code quality and implementation details. Provide working code examples. Consider performance, edge cases, and best practices. Be specific about language features and patterns.",
            tone_hint="technical",
        ),
    }


def get_default_models() -> Dict[str, ModelEntry]:
    """
    Return default model configurations.

    All models use GitHub Copilot API. Verified working via /chat/completions:
    - WORKING: gpt-4.1, gpt-5-mini, gpt-5.2, claude-sonnet-4.5, gpt-4o, gpt-4o-mini, gpt-4
    - NOT WORKING: claude-haiku-4.5, claude-sonnet-4, gpt-5, gpt-5.1, gemini-2.5-pro

    Note: Codex models (gpt-5.2-codex, etc.) require /responses endpoint, not /chat/completions.
    """
    return {
        # ============================================================
        # COPILOT MODELS - FREE/CHEAP TIER (enabled by default)
        # ============================================================
        "gpt-4.1": ModelEntry(
            name="gpt-4.1",
            provider=Provider.COPILOT,
            model_id="gpt-4.1",
            domain="general",
            weight=1.0,
            enabled=True,
        ),
        "gpt-5-mini": ModelEntry(
            name="gpt-5-mini",
            provider=Provider.COPILOT,
            model_id="gpt-5-mini",
            domain="general",
            weight=0.8,
            enabled=True,
        ),
        "gpt-4o-mini": ModelEntry(
            name="gpt-4o-mini",
            provider=Provider.COPILOT,
            model_id="gpt-4o-mini",
            domain="general",
            weight=0.8,
            enabled=True,
        ),
        # ============================================================
        # COPILOT MODELS - STANDARD TIER (disabled by default)
        # ============================================================
        "gpt-5.2": ModelEntry(
            name="gpt-5.2",
            provider=Provider.COPILOT,
            model_id="gpt-5.2",
            domain="general",
            weight=1.0,
            enabled=False,
        ),
        "claude-sonnet-4.5": ModelEntry(
            name="claude-sonnet-4.5",
            provider=Provider.COPILOT,
            model_id="claude-sonnet-4.5",
            domain="reasoning",
            weight=1.0,
            enabled=False,
        ),
        "gpt-4o": ModelEntry(
            name="gpt-4o",
            provider=Provider.COPILOT,
            model_id="gpt-4o",
            domain="general",
            weight=1.0,
            enabled=False,
        ),
        "gpt-4": ModelEntry(
            name="gpt-4",
            provider=Provider.COPILOT,
            model_id="gpt-4",
            domain="general",
            weight=1.0,
            enabled=False,
        ),
        # ============================================================
        # GROQ MODELS (Disabled by default - requires GROQ_API_KEY)
        # ============================================================
        "groq-llama": ModelEntry(
            name="groq-llama",
            provider=Provider.GROQ,
            model_id="llama-3.1-70b-versatile",
            domain="general",
            weight=0.9,
            api_key_env="GROQ_API_KEY",
            enabled=False,
        ),
    }


def get_default_groups() -> Dict[str, GroupConfig]:
    """Return default group configurations."""
    return {
        "default": GroupConfig(
            name="default",
            description="Free tier: GPT-4.1, GPT-5-mini, GPT-4o-mini",
            models=["gpt-4.1", "gpt-5-mini", "gpt-4o-mini"],
            persona="concise",
        ),
        "code": GroupConfig(
            name="code",
            description="Code-focused: GPT-4.1 + GPT-4o-mini",
            models=["gpt-4.1", "gpt-4o-mini"],
            persona="coder",
        ),
        "creative": GroupConfig(
            name="creative",
            description="Creative thinking and brainstorming",
            models=["gpt-4.1", "gpt-5-mini", "gpt-4o-mini"],
            persona="creative",
        ),
        "research": GroupConfig(
            name="research",
            description="Deep analysis and research tasks",
            models=["gpt-4.1", "gpt-5-mini", "gpt-4o-mini"],
            persona="analyst",
        ),
        "premium": GroupConfig(
            name="premium",
            description="Premium models: GPT-5.2, Claude Sonnet 4.5, GPT-4o",
            models=["gpt-5.2", "claude-sonnet-4.5", "gpt-4o"],
            persona="concise",
            enabled=False,  # Disabled by default - uses premium quota
        ),
    }


def create_default_config() -> VecnaConfig:
    """Create a default configuration."""
    return VecnaConfig(
        personas=get_default_personas(),
        models=get_default_models(),
        groups=get_default_groups(),
        memory=MemoryConfig(),  # Default memory config (PostgreSQL + Redis)
        active_group="default",
        active_persona="concise",
    )
