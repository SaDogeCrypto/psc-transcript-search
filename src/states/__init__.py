"""
States module - state-specific implementations.

Each state subdirectory contains:
- models/: State-specific model extensions
- scrapers/: Data source adapters
- pipeline/: State-specific pipeline stages

States are registered via the registry module.
"""

from src.states.registry import StateRegistry

# Import state modules to trigger registration
from src.states import florida

__all__ = [
    "StateRegistry",
]
