"""
Vecna Model Factory

Creates model adapters from configuration.
"""

import os
from typing import List, Optional
import logging

from vecna.config.schema import VecnaConfig, ModelEntry, Provider
from vecna.adapters.base import (
    BaseAdapter,
    ModelConfig,
    GroqAdapter,
    CopilotAdapter,
    OllamaAdapter,
    TransformersAdapter,
)
from vecna.adapters.openai_adapter import OpenAIAdapter
from vecna.adapters.anthropic_adapter import AnthropicAdapter

logger = logging.getLogger("vecna.config.factory")


def create_adapter_from_entry(
    entry: ModelEntry,
    persona_prompt: Optional[str] = None,
) -> Optional[BaseAdapter]:
    """
    Create a model adapter from a ModelEntry configuration.

    Args:
        entry: The model configuration entry
        persona_prompt: Optional persona prompt to inject

    Returns:
        BaseAdapter instance or None if model can't be created
    """
    # Check if model is enabled
    if not entry.enabled:
        logger.debug(f"Model '{entry.name}' is disabled, skipping")
        return None

    # Get API key from environment if specified
    api_key = None
    if entry.api_key_env:
        api_key = os.getenv(entry.api_key_env)
        if not api_key:
            logger.debug(f"Model '{entry.name}' missing API key from env var '{entry.api_key_env}'")
            return None

    # Build ModelConfig
    config = ModelConfig(
        name=entry.name,
        model_id=entry.model_id,
        domain=entry.domain,
        weight=entry.weight,
        temperature=entry.temperature,
        max_tokens=entry.max_tokens,
        api_key=api_key,
        base_url=entry.base_url,
        extra_params=entry.extra_params.copy() if entry.extra_params else {},
        persona=persona_prompt,
    )

    # Create appropriate adapter based on provider
    try:
        if entry.provider == Provider.OPENAI:
            return OpenAIAdapter(config)
        elif entry.provider == Provider.ANTHROPIC:
            return AnthropicAdapter(config)
        elif entry.provider == Provider.GROQ:
            return GroqAdapter(config)
        elif entry.provider == Provider.COPILOT:
            # Copilot doesn't need API key in config, uses auth module
            return _create_copilot_adapter(config, entry)
        elif entry.provider == Provider.OLLAMA:
            return OllamaAdapter(config)
        elif entry.provider == Provider.TRANSFORMERS:
            return TransformersAdapter(config)
        else:
            logger.warning(f"Unknown provider '{entry.provider}' for model '{entry.name}'")
            return None

    except Exception as e:
        logger.error(f"Failed to create adapter for '{entry.name}': {e}")
        return None


def _create_copilot_adapter(config: ModelConfig, entry: ModelEntry) -> Optional[BaseAdapter]:
    """Create a Copilot adapter if authentication is available."""
    try:
        from vecna.auth import CopilotAuth

        copilot = CopilotAuth()
        if not copilot.is_authenticated():
            logger.debug(f"Copilot model '{entry.name}' skipped - not authenticated")
            return None

        # Mark as copilot provider in extra_params
        config.extra_params["provider"] = "copilot"
        return CopilotAdapter(config)

    except ImportError:
        logger.debug("Copilot auth module not available")
        return None
    except Exception as e:
        logger.debug(f"Copilot adapter creation failed: {e}")
        return None


def create_adapters_from_config(
    config: VecnaConfig,
    model_names: Optional[List[str]] = None,
) -> List[BaseAdapter]:
    """
    Create all enabled adapters from a VecnaConfig.

    Args:
        config: The Vecna configuration
        model_names: Optional list of specific model names to create.
                    If None, uses the active group's models.

    Returns:
        List of created adapters
    """
    adapters = []

    # Determine which models to create
    if model_names is not None:
        # Use specified models
        entries = [config.models[name] for name in model_names if name in config.models]
    else:
        # Use active group's models
        entries = config.get_active_models()

    # Get active persona prompt
    active_persona = config.get_active_persona()
    default_persona_prompt = active_persona.prompt if active_persona else None

    for entry in entries:
        # Check for model-specific persona override
        persona_prompt = default_persona_prompt
        if entry.persona_override:
            override_persona = config.personas.get(entry.persona_override)
            if override_persona:
                persona_prompt = override_persona.prompt

        adapter = create_adapter_from_entry(entry, persona_prompt)
        if adapter:
            adapters.append(adapter)
            logger.info(f"Created adapter: {entry.name} (provider: {entry.provider.value})")

    return adapters


def get_available_model_names(config: VecnaConfig) -> List[str]:
    """
    Get list of model names that can be created (have valid credentials).
    """
    available = []

    for name, entry in config.models.items():
        if not entry.enabled:
            continue

        # Check API key availability
        if entry.api_key_env:
            if os.getenv(entry.api_key_env):
                available.append(name)
        elif entry.provider == Provider.COPILOT:
            try:
                from vecna.auth import CopilotAuth

                if CopilotAuth().is_authenticated():
                    available.append(name)
            except ImportError:
                pass
        elif entry.provider == Provider.OLLAMA:
            # Assume Ollama is available if configured
            available.append(name)

    return available
