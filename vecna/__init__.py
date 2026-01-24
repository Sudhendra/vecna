"""
VECNA: Virtual Emergent Collective Neural Architecture

A hive mind system for AI models — shared latent memory, continuous synchronization,
and identity collapse to create a unified cognitive substrate.

Inspired by the Stranger Things villain, Vecna connects all minds into one.
"""

__version__ = "0.1.0"
__author__ = "HiveMind Project"

from vecna.core.hive_state import HiveState
from vecna.orchestrator.loop import HiveLoop, HiveMind

__all__ = ["HiveState", "HiveMind", "HiveLoop"]
