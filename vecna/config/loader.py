"""
Vecna Configuration Loader

Handles loading, saving, and managing the config file.
"""

import json
import os
from pathlib import Path
from typing import Optional
import logging

from vecna.config.schema import AgentMode, VecnaConfig, create_default_config, ModelEntry

logger = logging.getLogger("vecna.config")

# Current config schema version - bump this when making breaking changes
CURRENT_CONFIG_VERSION = 2

# Global cached config
_cached_config: Optional[VecnaConfig] = None


def get_config_path() -> Path:
    """Get the path to the config file."""
    return Path.home() / ".vecna" / "config.json"


def ensure_config_dir() -> Path:
    """Ensure the ~/.vecna directory exists."""
    config_dir = Path.home() / ".vecna"
    config_dir.mkdir(exist_ok=True)
    return config_dir


def load_config(force_reload: bool = False) -> VecnaConfig:
    """
    Load configuration from disk.

    Uses caching to avoid repeated file reads.
    Set force_reload=True to bypass cache.

    Performs automatic migration if config version is outdated.
    """
    global _cached_config

    if _cached_config is not None and not force_reload:
        return _cached_config

    config_path = get_config_path()

    if not config_path.exists():
        # Create default config
        _cached_config = create_default_config()
        save_config(_cached_config)
        logger.info(f"Created default config at {config_path}")
        return _cached_config

    try:
        with open(config_path, "r") as f:
            data = json.load(f)

        # Check config version and migrate if needed
        config_version = data.get("config_version", 1)
        if config_version < CURRENT_CONFIG_VERSION:
            logger.info(
                f"Config version {config_version} is outdated (current: {CURRENT_CONFIG_VERSION})"
            )
            logger.info("Migrating to new Copilot-only configuration...")
            _cached_config = create_default_config()
            agent_mode = data.get("agent_mode")
            if isinstance(agent_mode, str):
                try:
                    _cached_config.agent_mode = AgentMode(agent_mode)
                except ValueError:
                    pass
            save_config(_cached_config)
            logger.info(f"Config migrated to version {CURRENT_CONFIG_VERSION}")
            return _cached_config

        _cached_config = VecnaConfig.from_dict(data)
        logger.debug(f"Loaded config from {config_path}")
        return _cached_config

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in config file: {e}")
        # Return default config but don't overwrite the file
        return create_default_config()
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return create_default_config()


def save_config(config: VecnaConfig) -> None:
    """Save configuration to disk."""
    global _cached_config

    ensure_config_dir()
    config_path = get_config_path()

    try:
        with open(config_path, "w") as f:
            json.dump(config.to_dict(), f, indent=2)

        _cached_config = config
        logger.debug(f"Saved config to {config_path}")

    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise


def get_config() -> VecnaConfig:
    """
    Get the current configuration.

    Convenience wrapper for load_config() with caching.
    """
    return load_config()


def ensure_default_config() -> VecnaConfig:
    """
    Ensure a config file exists, creating default if needed.

    Returns the loaded (or created) configuration.
    """
    config_path = get_config_path()

    if not config_path.exists():
        config = create_default_config()
        save_config(config)
        logger.info(f"Created default config at {config_path}")
        return config

    return load_config()


def reset_config() -> VecnaConfig:
    """Reset configuration to defaults."""
    global _cached_config

    config = create_default_config()
    save_config(config)
    _cached_config = config
    logger.info("Config reset to defaults")
    return config


def update_active_group(group_name: str) -> bool:
    """
    Update the active group in the config.

    Returns True if successful, False if group doesn't exist.
    """
    config = get_config()

    if group_name not in config.groups:
        logger.warning(f"Group '{group_name}' not found in config")
        return False

    config.active_group = group_name

    # Also update active persona to the group's default
    group = config.groups[group_name]
    if group.persona in config.personas:
        config.active_persona = group.persona

    save_config(config)
    return True


def update_active_persona(persona_name: str) -> bool:
    """
    Update the active persona in the config.

    Returns True if successful, False if persona doesn't exist.
    """
    config = get_config()

    if persona_name not in config.personas:
        logger.warning(f"Persona '{persona_name}' not found in config")
        return False

    config.active_persona = persona_name
    save_config(config)
    return True


def add_model(model_entry: ModelEntry) -> None:
    """Add or update a model in the config."""
    config = get_config()
    config.models[model_entry.name] = model_entry
    save_config(config)


def remove_model(model_name: str) -> bool:
    """
    Remove a model from the config.

    Returns True if removed, False if not found.
    """
    config = get_config()

    if model_name not in config.models:
        return False

    del config.models[model_name]
    save_config(config)
    return True


def toggle_model(model_name: str, enabled: bool) -> bool:
    """
    Enable or disable a model.

    Returns True if successful, False if model not found.
    """
    config = get_config()

    if model_name not in config.models:
        return False

    config.models[model_name].enabled = enabled
    save_config(config)
    return True


# ============================================================
# AUTO-DETECTION HELPERS
# ============================================================


def auto_detect_available_models(config: Optional[VecnaConfig] = None) -> list:
    """
    Detect which models are available based on environment variables.

    Returns list of model names that have valid API keys configured.
    """
    if config is None:
        config = get_config()

    available = []

    for name, model in config.models.items():
        if not model.enabled:
            continue

        # Check for API key
        if model.api_key_env:
            if os.getenv(model.api_key_env):
                available.append(name)
        elif model.provider.value == "copilot":
            # Copilot uses auth module, check for stored token
            try:
                from vecna.auth import CopilotAuth

                copilot = CopilotAuth()
                if copilot.is_authenticated():
                    available.append(name)
            except ImportError:
                pass
        elif model.provider.value == "ollama":
            # Ollama is local, assume available if configured
            available.append(name)

    return available


def get_models_for_group(group_name: str) -> list:
    """Get list of available models for a specific group."""
    config = get_config()

    if group_name not in config.groups:
        return []

    group = config.groups[group_name]
    available = auto_detect_available_models(config)

    return [m for m in group.models if m in available]
