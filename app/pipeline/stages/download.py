"""
Download Stage - Downloads audio from video sources.

Uses yt-dlp to extract audio from YouTube and other video platforms.
"""

import os
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.pipeline.stages.base import BaseStage, StageResult
from app.models.database import Hearing, PipelineJob

logger = logging.getLogger(__name__)

# Audio storage directory
AUDIO_DIR = Path(os.getenv("AUDIO_DIR", "data/audio"))


class DownloadStage(BaseStage):
    """Download audio from video URL using yt-dlp."""

    name = "download"
    in_progress_status = "downloading"
    complete_status = "transcribing"

    def __init__(self, audio_dir: Optional[Path] = None):
        self.audio_dir = audio_dir or AUDIO_DIR
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    def validate(self, hearing: Hearing, db: Session) -> bool:
        """Check if hearing has a video URL to download from."""
        if not hearing.video_url:
            logger.warning(f"Hearing {hearing.id} has no video_url")
            return False

        # Check if audio already exists
        audio_path = self._get_audio_path(hearing)
        if audio_path.exists():
            logger.info(f"Audio already exists for hearing {hearing.id}: {audio_path}")
            # Still valid - we'll skip the download
            return True

        return True

    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """Download audio from video URL."""
        audio_path = self._get_audio_path(hearing)

        # Skip if already downloaded
        if audio_path.exists():
            logger.info(f"Audio already exists, skipping download: {audio_path}")
            return StageResult(
                success=True,
                output={"audio_path": str(audio_path), "skipped": True},
                cost_usd=0.0
            )

        try:
            # Download using yt-dlp
            result = self._download_audio(hearing.video_url, audio_path)

            if result["success"]:
                return StageResult(
                    success=True,
                    output={
                        "audio_path": str(audio_path),
                        "duration_seconds": result.get("duration"),
                        "format": result.get("format", "mp3"),
                    },
                    cost_usd=0.0  # Downloads are free
                )
            else:
                return StageResult(
                    success=False,
                    error=result.get("error", "Download failed"),
                    should_retry=True
                )

        except subprocess.CalledProcessError as e:
            return StageResult(
                success=False,
                error=f"yt-dlp failed: {e.stderr[:500] if e.stderr else str(e)}",
                should_retry=True
            )
        except Exception as e:
            return StageResult(
                success=False,
                error=f"Download error: {str(e)}",
                should_retry=True
            )

    def _get_audio_path(self, hearing: Hearing) -> Path:
        """Get the audio file path for a hearing."""
        # Use external_id if available (e.g., YouTube video ID), otherwise hearing ID
        filename = hearing.external_id or f"hearing_{hearing.id}"
        # Sanitize filename
        filename = "".join(c for c in filename if c.isalnum() or c in "-_")
        return self.audio_dir / f"{filename}.mp3"

    def _download_audio(self, video_url: str, output_path: Path) -> dict:
        """
        Download audio using yt-dlp.

        Returns dict with success status and metadata.
        """
        logger.info(f"Downloading audio from: {video_url}")

        # Ensure parent directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # yt-dlp command
        cmd = [
            "yt-dlp",
            "-x",  # Extract audio only
            "--audio-format", "mp3",
            "--audio-quality", "0",  # Best quality
            "-o", str(output_path.with_suffix("")),  # yt-dlp adds extension
            "--no-playlist",  # Don't download playlists
            "--socket-timeout", "30",
            "--retries", "3",
            video_url
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                check=True
            )

            # Check if file was created
            # yt-dlp might add .mp3 even if we specified .mp3
            if not output_path.exists():
                # Try with yt-dlp's naming
                alt_path = output_path.with_suffix(".mp3.mp3")
                if alt_path.exists():
                    alt_path.rename(output_path)

            if output_path.exists():
                logger.info(f"Downloaded: {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)")
                return {"success": True}
            else:
                return {"success": False, "error": "Output file not created"}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Download timed out after 10 minutes"}
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr[:500] if e.stderr else str(e)
            logger.error(f"yt-dlp error: {error_msg}")
            return {"success": False, "error": error_msg}

    def on_error(self, hearing: Hearing, job: PipelineJob, result: StageResult, db: Session):
        """Clean up partial downloads on error."""
        audio_path = self._get_audio_path(hearing)
        if audio_path.exists():
            try:
                audio_path.unlink()
                logger.info(f"Cleaned up partial download: {audio_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up {audio_path}: {e}")
