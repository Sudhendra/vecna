"""
Vecna Configuration Module

Manages personas, models, groups, and runtime settings.
Configuration is stored in ~/.vecna/config.json
"""

from vecna.config.schema import (
    PersonaConfig,
    ModelEntry,
    GroupConfig,
    VecnaConfig,
    Provider,
)
from vecna.config.loader import (
    load_config,
    save_config,
    get_config,
    get_config_path,
    ensure_default_config,
    update_active_group,
    update_active_persona,
)
from vecna.config.factory import (
    create_adapter_from_entry,
    create_adapters_from_config,
    get_available_model_names,
)

__all__ = [
    # Schema
    "PersonaConfig",
    "ModelEntry",
    "GroupConfig",
    "VecnaConfig",
    "Provider",
    # Loader
    "load_config",
    "save_config",
    "get_config",
    "get_config_path",
    "ensure_default_config",
    "update_active_group",
    "update_active_persona",
    # Factory
    "create_adapter_from_entry",
    "create_adapters_from_config",
    "get_available_model_names",
]
