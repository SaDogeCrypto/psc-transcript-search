"""
Florida PSC configuration settings.

Environment variables:
- FL_DATABASE_URL: PostgreSQL connection string (local or Azure)
- FL_STORAGE_BACKEND: 'local' or 'azure'
- AZURE_STORAGE_CONNECTION_STRING: Azure Blob connection string
- FL_AZURE_CONTAINER: Azure container name for Florida docs
"""

import os
from dataclasses import dataclass, field
from typing import Optional, Literal


# Simple env helpers (avoid external dependency)
def env_str(key: str, default: str = "") -> str:
    return os.environ.get(key, default)

def env_int(key: str, default: int = 0) -> int:
    val = os.environ.get(key)
    return int(val) if val else default

def env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").lower()
    return val in ("true", "1", "yes") if val else default


@dataclass
class FloridaConfig:
    """Configuration for Florida PSC platform."""

    # Database (supports local PostgreSQL or Azure Flexible Server)
    database_url: str = "postgresql://localhost/psc_florida"

    # Florida PSC API endpoints
    clerk_office_base_url: str = "https://pscweb.floridapsc.com/api/ClerkOffice"
    thunderstone_base_url: str = "https://pscweb.floridapsc.com/api/thunderstone"

    # Storage backend: 'local' or 'azure'
    storage_backend: str = "local"

    # Local storage paths (when storage_backend='local')
    local_storage_path: str = "data/florida"
    audio_dir: str = "data/florida/audio"
    documents_dir: str = "data/florida/documents"

    # Azure Blob Storage (when storage_backend='azure')
    azure_storage_connection_string: str = ""
    azure_container_name: str = "florida-docs"

    # Rate limiting (requests per second)
    api_rate_limit: float = 2.0

    # Processing
    max_concurrent_downloads: int = 3

    @classmethod
    def from_env(cls) -> "FloridaConfig":
        """Load configuration from environment variables."""
        storage_backend = env_str("FL_STORAGE_BACKEND", "local")
        local_path = env_str("FL_LOCAL_STORAGE", "data/florida")

        return cls(
            # Database - Azure PostgreSQL or local
            database_url=env_str(
                "FL_DATABASE_URL",
                "postgresql://localhost/psc_florida"
            ),

            # PSC API endpoints
            clerk_office_base_url=env_str(
                "FL_CLERK_OFFICE_URL",
                "https://pscweb.floridapsc.com/api/ClerkOffice"
            ),
            thunderstone_base_url=env_str(
                "FL_THUNDERSTONE_URL",
                "https://pscweb.floridapsc.com/api/thunderstone"
            ),

            # Storage backend
            storage_backend=storage_backend,

            # Local storage
            local_storage_path=local_path,
            audio_dir=env_str("FL_AUDIO_DIR", f"{local_path}/audio"),
            documents_dir=env_str("FL_DOCUMENTS_DIR", f"{local_path}/documents"),

            # Azure Blob Storage
            azure_storage_connection_string=env_str(
                "AZURE_STORAGE_CONNECTION_STRING", ""
            ),
            azure_container_name=env_str("FL_AZURE_CONTAINER", "florida-docs"),

            # Rate limiting
            api_rate_limit=float(env_str("FL_API_RATE_LIMIT", "2.0")),
            max_concurrent_downloads=env_int("FL_MAX_CONCURRENT_DOWNLOADS", 3),
        )

    @property
    def is_azure(self) -> bool:
        """Check if using Azure storage."""
        return self.storage_backend == "azure"

    @property
    def is_azure_db(self) -> bool:
        """Check if using Azure PostgreSQL."""
        return "azure" in self.database_url.lower() or "database.azure.com" in self.database_url


# Global config instance
_config: Optional[FloridaConfig] = None


def get_config() -> FloridaConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = FloridaConfig.from_env()
    return _config


def reload_config() -> FloridaConfig:
    """Reload configuration from environment."""
    global _config
    _config = FloridaConfig.from_env()
    return _config
