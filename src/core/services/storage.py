"""
Storage service - file storage abstraction.

Supports:
- Local filesystem storage
- Azure Blob Storage

Automatically selects backend based on configuration.
"""

import logging
from pathlib import Path
from typing import Optional, BinaryIO
from abc import ABC, abstractmethod

from src.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class StorageBackend(ABC):
    """Abstract storage backend interface."""

    @abstractmethod
    def upload(self, key: str, data: BinaryIO, content_type: str = None) -> str:
        """Upload file and return URL/path."""
        pass

    @abstractmethod
    def download(self, key: str) -> Optional[bytes]:
        """Download file by key."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if file exists."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete file by key."""
        pass

    @abstractmethod
    def get_url(self, key: str) -> str:
        """Get URL for file."""
        pass


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using local storage: {self.base_dir}")

    def _get_path(self, key: str) -> Path:
        """Get full path for key."""
        return self.base_dir / key

    def upload(self, key: str, data: BinaryIO, content_type: str = None) -> str:
        """Save file to local filesystem."""
        path = self._get_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'wb') as f:
            f.write(data.read())

        logger.debug(f"Uploaded to local: {path}")
        return str(path)

    def download(self, key: str) -> Optional[bytes]:
        """Read file from local filesystem."""
        path = self._get_path(key)
        if not path.exists():
            return None

        with open(path, 'rb') as f:
            return f.read()

    def exists(self, key: str) -> bool:
        """Check if file exists locally."""
        return self._get_path(key).exists()

    def delete(self, key: str) -> bool:
        """Delete local file."""
        path = self._get_path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def get_url(self, key: str) -> str:
        """Get local file path as URL."""
        return str(self._get_path(key))


class AzureBlobStorageBackend(StorageBackend):
    """Azure Blob Storage backend."""

    def __init__(self, connection_string: str, container_name: str):
        from azure.storage.blob import BlobServiceClient

        self.container_name = container_name
        self.blob_service = BlobServiceClient.from_connection_string(connection_string)
        self.container_client = self.blob_service.get_container_client(container_name)

        # Create container if it doesn't exist
        try:
            self.container_client.create_container()
            logger.info(f"Created Azure blob container: {container_name}")
        except Exception:
            pass  # Container already exists

        logger.info(f"Using Azure Blob Storage: {container_name}")

    def upload(self, key: str, data: BinaryIO, content_type: str = None) -> str:
        """Upload file to Azure Blob Storage."""
        blob_client = self.container_client.get_blob_client(key)

        content_settings = None
        if content_type:
            from azure.storage.blob import ContentSettings
            content_settings = ContentSettings(content_type=content_type)

        blob_client.upload_blob(data, overwrite=True, content_settings=content_settings)
        logger.debug(f"Uploaded to Azure: {key}")

        return blob_client.url

    def download(self, key: str) -> Optional[bytes]:
        """Download file from Azure Blob Storage."""
        try:
            blob_client = self.container_client.get_blob_client(key)
            return blob_client.download_blob().readall()
        except Exception:
            return None

    def exists(self, key: str) -> bool:
        """Check if blob exists."""
        blob_client = self.container_client.get_blob_client(key)
        return blob_client.exists()

    def delete(self, key: str) -> bool:
        """Delete blob."""
        try:
            blob_client = self.container_client.get_blob_client(key)
            blob_client.delete_blob()
            return True
        except Exception:
            return False

    def get_url(self, key: str) -> str:
        """Get blob URL."""
        blob_client = self.container_client.get_blob_client(key)
        return blob_client.url


class StorageService:
    """
    High-level storage service.

    Automatically selects backend based on configuration:
    - Local: Uses filesystem under audio_dir
    - Azure: Uses Azure Blob Storage

    Usage:
        storage = StorageService()
        storage.upload_audio("FL", "hearing_123.mp3", file_data)
        audio_bytes = storage.download_audio("FL", "hearing_123.mp3")
    """

    def __init__(self):
        if settings.storage_type == "azure" and settings.azure_storage_connection_string:
            self.backend = AzureBlobStorageBackend(
                settings.azure_storage_connection_string,
                settings.azure_storage_container
            )
        else:
            self.backend = LocalStorageBackend(settings.audio_dir)

    def upload_audio(
        self,
        state_code: str,
        filename: str,
        data: BinaryIO
    ) -> str:
        """
        Upload audio file.

        Args:
            state_code: Two-letter state code (FL, TX, etc.)
            filename: Audio filename
            data: File data

        Returns:
            URL or path to uploaded file
        """
        key = f"{state_code.lower()}/{filename}"

        # Determine content type
        content_type = "audio/mpeg"
        if filename.endswith(".m4a"):
            content_type = "audio/mp4"
        elif filename.endswith(".wav"):
            content_type = "audio/wav"

        return self.backend.upload(key, data, content_type)

    def download_audio(self, state_code: str, filename: str) -> Optional[bytes]:
        """Download audio file."""
        key = f"{state_code.lower()}/{filename}"
        return self.backend.download(key)

    def audio_exists(self, state_code: str, filename: str) -> bool:
        """Check if audio file exists."""
        key = f"{state_code.lower()}/{filename}"
        return self.backend.exists(key)

    def get_audio_url(self, state_code: str, filename: str) -> str:
        """Get URL for audio file."""
        key = f"{state_code.lower()}/{filename}"
        return self.backend.get_url(key)

    def delete_audio(self, state_code: str, filename: str) -> bool:
        """Delete audio file."""
        key = f"{state_code.lower()}/{filename}"
        return self.backend.delete(key)
