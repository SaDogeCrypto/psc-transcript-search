"""
Configuration management using Pydantic Settings.

Loads configuration from environment variables and .env file.
"""

import os
from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Database
    database_url: str = "postgresql://psc:psc_dev@localhost:5432/psc_dev"

    # Storage
    storage_type: str = "local"  # "local" or "azure"
    audio_dir: str = "data/audio"
    azure_storage_connection_string: Optional[str] = None
    azure_storage_container: str = "audio"

    # Whisper transcription (checked in priority order)
    groq_api_key: Optional[str] = None
    groq_whisper_model: str = "whisper-large-v3-turbo"

    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    azure_openai_api_version: str = "2024-06-01"
    azure_whisper_deployment: str = "whisper"

    openai_api_key: Optional[str] = None
    whisper_model: str = "whisper-1"

    # Analysis (GPT-4o-mini)
    analysis_model: str = "gpt-4o-mini"

    # State configuration
    active_states: str = "FL"

    # API settings
    api_secret_key: str = "dev-secret-change-in-production"
    admin_api_key: str = "admin-key-change-in-production"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Logging
    log_level: str = "INFO"

    @property
    def active_state_list(self) -> List[str]:
        """Parse comma-separated state codes into list."""
        return [s.strip().upper() for s in self.active_states.split(",") if s.strip()]

    @property
    def whisper_provider(self) -> str:
        """Determine which Whisper provider to use (priority order)."""
        if self.groq_api_key:
            return "groq"
        elif self.azure_openai_endpoint and self.azure_openai_api_key:
            return "azure"
        elif self.openai_api_key:
            return "openai"
        return "none"

    @property
    def has_analysis_capability(self) -> bool:
        """Check if analysis API is configured."""
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
