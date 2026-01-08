"""
State registry - plugin system for state implementations.

Allows states to register their:
- Scrapers (data source adapters)
- Pipeline stages (state-specific processing)
- Configuration (API endpoints, credentials)

Usage:
    # Register a scraper
    StateRegistry.register_scraper("FL", "clerk_office", ClerkOfficeScraper)

    # Get a scraper
    scraper_class = StateRegistry.get_scraper("FL", "clerk_office")
    scraper = scraper_class(db)
    result = scraper.scrape()

    # List available states
    states = StateRegistry.get_available_states()  # ["FL", "TX", ...]
"""

import logging
from typing import Dict, Type, List, Optional, Any

from src.core.scrapers.base import Scraper
from src.core.pipeline.base import PipelineStage

logger = logging.getLogger(__name__)


class StateRegistry:
    """
    Registry for state-specific implementations.

    Provides a plugin system where each state can register
    its own scrapers, pipeline stages, and configuration.
    """

    # State scrapers: {state_code: {scraper_name: ScraperClass}}
    _scrapers: Dict[str, Dict[str, Type[Scraper]]] = {}

    # State pipeline stages: {state_code: {stage_name: StageClass}}
    _stages: Dict[str, Dict[str, Type[PipelineStage]]] = {}

    # State configuration: {state_code: config_dict}
    _configs: Dict[str, Dict[str, Any]] = {}

    # State metadata
    _metadata: Dict[str, Dict[str, Any]] = {}

    @classmethod
    def register_scraper(cls, state_code: str, name: str, scraper_class: Type[Scraper]):
        """
        Register a scraper for a state.

        Args:
            state_code: Two-letter state code (FL, TX, etc.)
            name: Scraper identifier (e.g., "clerk_office", "thunderstone")
            scraper_class: The scraper class to register
        """
        state_code = state_code.upper()
        if state_code not in cls._scrapers:
            cls._scrapers[state_code] = {}

        cls._scrapers[state_code][name] = scraper_class
        logger.debug(f"Registered scraper: {state_code}/{name}")

    @classmethod
    def register_stage(cls, state_code: str, name: str, stage_class: Type[PipelineStage]):
        """
        Register a pipeline stage for a state.

        Args:
            state_code: Two-letter state code
            name: Stage identifier (e.g., "docket_sync", "document_sync")
            stage_class: The stage class to register
        """
        state_code = state_code.upper()
        if state_code not in cls._stages:
            cls._stages[state_code] = {}

        cls._stages[state_code][name] = stage_class
        logger.debug(f"Registered stage: {state_code}/{name}")

    @classmethod
    def register_config(cls, state_code: str, config: Dict[str, Any]):
        """
        Register configuration for a state.

        Args:
            state_code: Two-letter state code
            config: Configuration dictionary
        """
        state_code = state_code.upper()
        cls._configs[state_code] = config
        logger.debug(f"Registered config for: {state_code}")

    @classmethod
    def register_metadata(cls, state_code: str, metadata: Dict[str, Any]):
        """
        Register metadata for a state.

        Metadata includes:
        - full_name: Full state name
        - commission_name: Name of the PSC/PUC
        - website: Commission website URL
        - docket_format: Regex pattern for docket numbers

        Args:
            state_code: Two-letter state code
            metadata: Metadata dictionary
        """
        state_code = state_code.upper()
        cls._metadata[state_code] = metadata
        logger.debug(f"Registered metadata for: {state_code}")

    @classmethod
    def get_scraper(cls, state_code: str, name: str) -> Optional[Type[Scraper]]:
        """
        Get scraper class by state and name.

        Args:
            state_code: Two-letter state code
            name: Scraper identifier

        Returns:
            Scraper class, or None if not found
        """
        state_code = state_code.upper()
        return cls._scrapers.get(state_code, {}).get(name)

    @classmethod
    def get_stage(cls, state_code: str, name: str) -> Optional[Type[PipelineStage]]:
        """
        Get pipeline stage by state and name.

        Args:
            state_code: Two-letter state code
            name: Stage identifier

        Returns:
            Stage class, or None if not found
        """
        state_code = state_code.upper()
        return cls._stages.get(state_code, {}).get(name)

    @classmethod
    def get_config(cls, state_code: str) -> Dict[str, Any]:
        """
        Get configuration for a state.

        Args:
            state_code: Two-letter state code

        Returns:
            Configuration dictionary (empty if not registered)
        """
        state_code = state_code.upper()
        return cls._configs.get(state_code, {})

    @classmethod
    def get_metadata(cls, state_code: str) -> Dict[str, Any]:
        """
        Get metadata for a state.

        Args:
            state_code: Two-letter state code

        Returns:
            Metadata dictionary (empty if not registered)
        """
        state_code = state_code.upper()
        return cls._metadata.get(state_code, {})

    @classmethod
    def get_available_states(cls) -> List[str]:
        """
        Get list of registered state codes.

        Returns:
            List of state codes that have scrapers or stages registered
        """
        states = set(cls._scrapers.keys()) | set(cls._stages.keys())
        return sorted(list(states))

    @classmethod
    def get_state_scrapers(cls, state_code: str) -> List[str]:
        """
        Get available scraper names for a state.

        Args:
            state_code: Two-letter state code

        Returns:
            List of scraper names
        """
        state_code = state_code.upper()
        return list(cls._scrapers.get(state_code, {}).keys())

    @classmethod
    def get_state_stages(cls, state_code: str) -> List[str]:
        """
        Get available stage names for a state.

        Args:
            state_code: Two-letter state code

        Returns:
            List of stage names
        """
        state_code = state_code.upper()
        return list(cls._stages.get(state_code, {}).keys())

    @classmethod
    def get_all_scrapers(cls) -> Dict[str, List[str]]:
        """
        Get all registered scrapers.

        Returns:
            Dict mapping state codes to lists of scraper names
        """
        return {
            state: list(scrapers.keys())
            for state, scrapers in cls._scrapers.items()
        }

    @classmethod
    def get_all_stages(cls) -> Dict[str, List[str]]:
        """
        Get all registered stages.

        Returns:
            Dict mapping state codes to lists of stage names
        """
        return {
            state: list(stages.keys())
            for state, stages in cls._stages.items()
        }
