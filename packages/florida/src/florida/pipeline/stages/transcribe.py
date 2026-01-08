"""
Florida Transcribe Stage - Transcribes audio using Whisper.

Adapts the core transcription logic to work with Florida models
(FLHearing, FLTranscriptSegment).

Supports:
- Groq Whisper API (fastest, preferred)
- Azure OpenAI Whisper API
- OpenAI Whisper API
"""

import os
import logging
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

from sqlalchemy.orm import Session

from florida.models.hearing import FLHearing, FLTranscriptSegment

logger = logging.getLogger(__name__)

# Configuration from environment
AUDIO_DIR = Path(os.getenv("FL_AUDIO_DIR", os.getenv("AUDIO_DIR", "data/audio")))
USE_OPENAI_WHISPER = os.getenv("USE_OPENAI_WHISPER", "true").lower() == "true"

# File size limits for chunking
MAX_FILE_SIZE_BYTES = 24 * 1024 * 1024  # 24MB (Groq limit is 25MB)
CHUNK_DURATION_SECONDS = 600  # 10 minutes per chunk

# Groq configuration (preferred - fastest)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")

# Azure OpenAI configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
AZURE_WHISPER_DEPLOYMENT = os.getenv("AZURE_WHISPER_DEPLOYMENT", "whisper")

# OpenAI configuration
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")

# Pricing
WHISPER_COST_PER_MINUTE = 0.006  # $0.006/min (OpenAI/Azure)
GROQ_WHISPER_COST_PER_MINUTE = 0.04 / 60  # $0.04/hour


@dataclass
class TranscriptionResult:
    """Result of transcription."""
    success: bool
    text: str = ""
    segments: List[Dict[str, Any]] = None
    model: str = ""
    cost_usd: float = 0.0
    error: str = ""

    def __post_init__(self):
        if self.segments is None:
            self.segments = []


class FLTranscribeStage:
    """
    Transcribe audio for Florida hearings using Whisper.

    Adapts the main app's TranscribeStage logic to work with
    Florida's FLHearing and FLTranscriptSegment models.
    """

    name = "transcribe"

    def __init__(self, audio_dir: Optional[Path] = None):
        self.audio_dir = audio_dir or AUDIO_DIR
        self._openai_client = None
        self._groq_client = None
        # Priority: Groq > Azure > OpenAI
        self._use_groq = bool(GROQ_API_KEY)
        self._use_azure = bool(AZURE_OPENAI_ENDPOINT) and not self._use_groq

    @property
    def groq_client(self):
        """Lazy load Groq client."""
        if self._groq_client is None and self._use_groq:
            from groq import Groq
            self._groq_client = Groq(api_key=GROQ_API_KEY)
            logger.info("Using Groq Whisper API (fastest)")
        return self._groq_client

    @property
    def openai_client(self):
        """Lazy load OpenAI client."""
        if self._openai_client is None and USE_OPENAI_WHISPER and not self._use_groq:
            if self._use_azure:
                from openai import AzureOpenAI
                self._openai_client = AzureOpenAI(
                    azure_endpoint=AZURE_OPENAI_ENDPOINT,
                    api_key=AZURE_OPENAI_API_KEY,
                    api_version=AZURE_OPENAI_API_VERSION,
                )
                logger.info(f"Using Azure OpenAI Whisper: {AZURE_OPENAI_ENDPOINT}")
            else:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                logger.info("Using OpenAI Whisper API")
        return self._openai_client

    def _build_initial_prompt(self, hearing: FLHearing) -> str:
        """Build Whisper initial_prompt with Florida PSC context."""
        prompt_parts = [
            "This is a Florida Public Service Commission hearing transcript.",
            "Technical terms: kilowatt, megawatt, FPSC, docket, tariff, rate case, "
            "certificate, intervenor, stipulation, evidentiary hearing, pre-filed testimony.",
            "Florida PSC, FPSC, Florida Power & Light, FPL, Duke Energy Florida, "
            "Tampa Electric, TECO, NextEra, Gulf Power, JEA.",
            "Chairman Fay, Commissioner Clark, Commissioner La Rosa, Commissioner Passidomo, "
            "Commissioner Graham.",
            "Docket numbers like 20250035-GU, 20240001-EI.",
        ]

        if hearing.title:
            prompt_parts.append(f"Hearing: {hearing.title[:200]}")

        return " ".join(prompt_parts)

    def validate(self, hearing: FLHearing, db: Session) -> Tuple[bool, str]:
        """Check if hearing can be transcribed."""
        audio_path = self._get_audio_path(hearing)

        # Audio will be downloaded if not present, so check for source_url instead
        if not audio_path.exists() and not hearing.source_url:
            return False, f"No audio file or source URL for hearing {hearing.id}"

        # Check if already transcribed (has segments)
        segment_count = db.query(FLTranscriptSegment).filter(
            FLTranscriptSegment.hearing_id == hearing.id
        ).count()

        if segment_count > 0:
            return False, f"Already transcribed ({segment_count} segments)"

        return True, ""

    def execute(self, hearing: FLHearing, db: Session) -> TranscriptionResult:
        """Transcribe audio for a Florida hearing."""
        audio_path = self._get_audio_path(hearing)

        # Download audio if it doesn't exist
        if not audio_path.exists():
            logger.info(f"Audio not found for hearing {hearing.id}, downloading...")
            downloaded_path = self._download_audio(hearing)
            if downloaded_path:
                audio_path = downloaded_path
            else:
                return TranscriptionResult(
                    success=False,
                    error=f"Failed to download audio from {hearing.source_url}"
                )

        # Check if already transcribed
        existing_count = db.query(FLTranscriptSegment).filter(
            FLTranscriptSegment.hearing_id == hearing.id
        ).count()

        if existing_count > 0:
            return TranscriptionResult(
                success=True,
                text=hearing.full_text or "",
                error="Already transcribed (skipped)"
            )

        try:
            # Build initial prompt for better accuracy
            initial_prompt = self._build_initial_prompt(hearing)
            logger.debug(f"Using initial_prompt: {initial_prompt[:100]}...")

            # Transcribe using appropriate provider
            result = self._transcribe(audio_path, hearing, initial_prompt)

            if not result.success:
                return result

            # Save to database
            self._save_transcript(hearing, result, db)

            return result

        except Exception as e:
            logger.exception(f"Transcription error for hearing {hearing.id}")
            return TranscriptionResult(
                success=False,
                error=f"Transcription error: {str(e)}"
            )

    def _get_audio_path(self, hearing: FLHearing) -> Path:
        """Get audio file path for a hearing."""
        import hashlib

        # Try multiple filename formats
        filenames_to_try = []

        # 1. Hash-based format (legacy RSS scraper format)
        if hearing.external_id or hearing.source_url:
            url = hearing.external_id or hearing.source_url
            hash_id = hashlib.md5(url.encode()).hexdigest()[:16]
            filenames_to_try.append(f"rss_{hash_id}")

        # 2. Sanitized external_id format
        if hearing.external_id:
            sanitized = "".join(c for c in hearing.external_id if c.isalnum() or c in "-_")
            filenames_to_try.append(sanitized)

        # 3. Hearing ID format
        filenames_to_try.append(f"hearing_{hearing.id}")

        # Check each filename with common extensions
        for filename in filenames_to_try:
            for ext in [".mp3", ".m4a", ".wav", ".mp4"]:
                path = self.audio_dir / f"{filename}{ext}"
                if path.exists():
                    logger.debug(f"Found audio file: {path}")
                    return path

        # Return default path for download
        if filenames_to_try:
            return self.audio_dir / f"{filenames_to_try[0]}.mp3"
        return self.audio_dir / f"hearing_{hearing.id}.mp3"

    def _download_audio(self, hearing: FLHearing) -> Optional[Path]:
        """Download audio from video URL using yt-dlp."""
        import hashlib

        if not hearing.source_url:
            logger.warning(f"No source_url for hearing {hearing.id}")
            return None

        # Create audio directory if needed
        self.audio_dir.mkdir(parents=True, exist_ok=True)

        # Use hash-based filename (matches legacy format)
        url = hearing.external_id or hearing.source_url
        hash_id = hashlib.md5(url.encode()).hexdigest()[:16]
        filename = f"rss_{hash_id}"
        output_path = self.audio_dir / f"{filename}.mp3"

        if output_path.exists():
            logger.info(f"Audio already exists: {output_path}")
            return output_path

        logger.info(f"Downloading audio from {hearing.source_url}")

        try:
            result = subprocess.run(
                [
                    "yt-dlp",
                    "-x",  # Extract audio
                    "--audio-format", "mp3",
                    "--audio-quality", "4",  # Good quality, smaller file
                    "-o", str(output_path.with_suffix(".%(ext)s")),
                    "--no-playlist",
                    "--impersonate", "chrome",  # Use browser impersonation for Cloudflare
                    "--extractor-args", "generic:impersonate",
                    hearing.source_url
                ],
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"yt-dlp error: {result.stderr}")
                return None

            # yt-dlp may create file with different extension then convert
            if output_path.exists():
                return output_path

            # Check for other extensions
            for ext in [".mp3", ".m4a", ".wav", ".webm"]:
                alt_path = output_path.with_suffix(ext)
                if alt_path.exists():
                    return alt_path

            logger.error(f"Audio file not found after download")
            return None

        except subprocess.TimeoutExpired:
            logger.error(f"Download timeout for hearing {hearing.id}")
            return None
        except Exception as e:
            logger.error(f"Download error for hearing {hearing.id}: {e}")
            return None

    def _needs_chunking(self, audio_path: Path) -> bool:
        """Check if audio exceeds size limit."""
        return audio_path.stat().st_size > MAX_FILE_SIZE_BYTES

    def _transcribe(self, audio_path: Path, hearing: FLHearing, initial_prompt: str) -> TranscriptionResult:
        """Transcribe audio using the best available provider."""
        if self._needs_chunking(audio_path):
            return self._transcribe_chunked(audio_path, hearing, initial_prompt)

        if self._use_groq:
            return self._transcribe_groq(audio_path, hearing, initial_prompt)

        return self._transcribe_openai(audio_path, hearing, initial_prompt)

    def _transcribe_groq(self, audio_path: Path, hearing: FLHearing, initial_prompt: str) -> TranscriptionResult:
        """Transcribe using Groq Whisper API."""
        logger.info(f"Transcribing with Groq Whisper: {audio_path.name}")

        duration_seconds = hearing.duration_seconds or self._get_audio_duration(audio_path)
        duration_minutes = (duration_seconds or 0) / 60

        try:
            with open(audio_path, "rb") as audio_file:
                response = self.groq_client.audio.transcriptions.create(
                    model=GROQ_WHISPER_MODEL,
                    file=audio_file,
                    response_format="verbose_json",
                    prompt=initial_prompt if initial_prompt else None,
                )

            full_text = response.text
            segments = []

            if hasattr(response, 'segments') and response.segments:
                for i, seg in enumerate(response.segments):
                    if isinstance(seg, dict):
                        segments.append({
                            "index": i,
                            "start": seg.get("start", 0),
                            "end": seg.get("end", 0),
                            "text": seg.get("text", "").strip(),
                        })
                    else:
                        segments.append({
                            "index": i,
                            "start": getattr(seg, "start", 0),
                            "end": getattr(seg, "end", 0),
                            "text": getattr(seg, "text", "").strip(),
                        })

            cost_usd = duration_minutes * GROQ_WHISPER_COST_PER_MINUTE
            logger.info(f"Groq transcription complete: {len(segments)} segments, {duration_minutes:.1f} min")

            return TranscriptionResult(
                success=True,
                text=full_text,
                segments=segments,
                model=GROQ_WHISPER_MODEL,
                cost_usd=cost_usd,
            )

        except Exception as e:
            logger.error(f"Groq transcription error: {e}")
            return TranscriptionResult(success=False, error=str(e))

    def _transcribe_openai(self, audio_path: Path, hearing: FLHearing, initial_prompt: str) -> TranscriptionResult:
        """Transcribe using OpenAI/Azure Whisper API."""
        model_name = AZURE_WHISPER_DEPLOYMENT if self._use_azure else WHISPER_MODEL
        provider = "Azure OpenAI" if self._use_azure else "OpenAI"

        logger.info(f"Transcribing with {provider} Whisper: {audio_path.name}")

        duration_seconds = hearing.duration_seconds or self._get_audio_duration(audio_path)
        duration_minutes = (duration_seconds or 0) / 60

        try:
            with open(audio_path, "rb") as audio_file:
                response = self.openai_client.audio.transcriptions.create(
                    model=model_name,
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                    prompt=initial_prompt if initial_prompt else None,
                )

            full_text = response.text
            segments = []

            if hasattr(response, 'segments') and response.segments:
                for i, seg in enumerate(response.segments):
                    if isinstance(seg, dict):
                        segments.append({
                            "index": i,
                            "start": seg.get("start", 0),
                            "end": seg.get("end", 0),
                            "text": seg.get("text", "").strip(),
                        })
                    else:
                        segments.append({
                            "index": i,
                            "start": getattr(seg, "start", 0),
                            "end": getattr(seg, "end", 0),
                            "text": getattr(seg, "text", "").strip(),
                        })

            cost_usd = duration_minutes * WHISPER_COST_PER_MINUTE
            logger.info(f"{provider} transcription complete: {len(segments)} segments, ${cost_usd:.4f}")

            return TranscriptionResult(
                success=True,
                text=full_text,
                segments=segments,
                model=model_name,
                cost_usd=cost_usd,
            )

        except Exception as e:
            logger.error(f"{provider} transcription error: {e}")
            return TranscriptionResult(success=False, error=str(e))

    def _transcribe_chunked(self, audio_path: Path, hearing: FLHearing, initial_prompt: str) -> TranscriptionResult:
        """Transcribe large audio by splitting into chunks."""
        if self._use_groq:
            model_name = GROQ_WHISPER_MODEL
            provider = "Groq"
            cost_per_minute = GROQ_WHISPER_COST_PER_MINUTE
        elif self._use_azure:
            model_name = AZURE_WHISPER_DEPLOYMENT
            provider = "Azure OpenAI"
            cost_per_minute = WHISPER_COST_PER_MINUTE
        else:
            model_name = WHISPER_MODEL
            provider = "OpenAI"
            cost_per_minute = WHISPER_COST_PER_MINUTE

        file_size_mb = audio_path.stat().st_size / (1024 * 1024)
        logger.info(f"File {audio_path.name} is {file_size_mb:.1f}MB - splitting into chunks ({provider})")

        duration_seconds = hearing.duration_seconds or self._get_audio_duration(audio_path)
        duration_minutes = (duration_seconds or 0) / 60

        chunks = []
        try:
            chunks = self._split_audio(audio_path, duration_seconds or 0)
            logger.info(f"Created {len(chunks)} chunks")

            all_segments = []
            all_text_parts = []
            segment_index = 0

            for chunk_path, time_offset in chunks:
                logger.info(f"Transcribing chunk: {chunk_path.name} (offset={time_offset}s)")

                try:
                    with open(chunk_path, "rb") as audio_file:
                        if self._use_groq:
                            response = self.groq_client.audio.transcriptions.create(
                                model=model_name,
                                file=audio_file,
                                response_format="verbose_json",
                                prompt=initial_prompt if initial_prompt else None,
                            )
                        else:
                            response = self.openai_client.audio.transcriptions.create(
                                model=model_name,
                                file=audio_file,
                                response_format="verbose_json",
                                timestamp_granularities=["segment"],
                                prompt=initial_prompt if initial_prompt else None,
                            )

                    if response.text:
                        all_text_parts.append(response.text)

                    if hasattr(response, 'segments') and response.segments:
                        for seg in response.segments:
                            if isinstance(seg, dict):
                                start = seg.get("start", 0)
                                end = seg.get("end", 0)
                                text = seg.get("text", "").strip()
                            else:
                                start = getattr(seg, "start", 0)
                                end = getattr(seg, "end", 0)
                                text = getattr(seg, "text", "").strip()

                            all_segments.append({
                                "index": segment_index,
                                "start": start + time_offset,
                                "end": end + time_offset,
                                "text": text,
                            })
                            segment_index += 1

                except Exception as e:
                    logger.error(f"Error transcribing chunk {chunk_path.name}: {e}")
                    continue

            if not all_segments:
                return TranscriptionResult(success=False, error="No segments transcribed from chunks")

            full_text = " ".join(all_text_parts)
            cost_usd = duration_minutes * cost_per_minute

            logger.info(f"{provider} chunked transcription complete: {len(all_segments)} segments")

            return TranscriptionResult(
                success=True,
                text=full_text,
                segments=all_segments,
                model=model_name,
                cost_usd=cost_usd,
            )

        except Exception as e:
            return TranscriptionResult(success=False, error=str(e))

        finally:
            self._cleanup_chunks(chunks)

    def _split_audio(self, audio_path: Path, duration: float) -> List[Tuple[Path, float]]:
        """Split audio into chunks using ffmpeg."""
        if duration == 0:
            duration = self._get_audio_duration(audio_path) or 0
            if duration == 0:
                raise ValueError(f"Could not determine duration of {audio_path}")

        chunks = []
        temp_dir = tempfile.mkdtemp(prefix="fl_whisper_chunks_")
        num_chunks = int((duration // CHUNK_DURATION_SECONDS) + 1)

        logger.info(f"Splitting {audio_path.name} ({duration}s) into {num_chunks} chunks")

        for i in range(num_chunks):
            start_time = i * CHUNK_DURATION_SECONDS
            chunk_path = Path(temp_dir) / f"chunk_{i:03d}.mp3"

            try:
                result = subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-i", str(audio_path),
                        "-ss", str(start_time),
                        "-t", str(CHUNK_DURATION_SECONDS),
                        "-c:a", "libmp3lame",
                        "-q:a", "4",
                        str(chunk_path)
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120
                )

                if result.returncode == 0 and chunk_path.exists() and chunk_path.stat().st_size > 0:
                    chunks.append((chunk_path, float(start_time)))

            except Exception as e:
                logger.error(f"Error creating chunk {i}: {e}")
                continue

        if not chunks:
            raise ValueError(f"Failed to create any chunks from {audio_path}")

        return chunks

    def _cleanup_chunks(self, chunks: List[Tuple[Path, float]]):
        """Remove temporary chunk files."""
        if not chunks:
            return

        temp_dir = chunks[0][0].parent
        for chunk_path, _ in chunks:
            try:
                chunk_path.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            temp_dir.rmdir()
        except Exception:
            pass

    def _save_transcript(self, hearing: FLHearing, result: TranscriptionResult, db: Session):
        """Save transcript to FLHearing and create FLTranscriptSegment records."""
        # Update hearing with transcript
        hearing.full_text = result.text
        hearing.word_count = len(result.text.split()) if result.text else 0
        hearing.whisper_model = result.model
        hearing.processing_cost_usd = result.cost_usd
        hearing.transcript_status = "transcribed"
        hearing.processed_at = datetime.utcnow()

        # Create segment records
        for seg_data in result.segments:
            segment = FLTranscriptSegment(
                hearing_id=hearing.id,
                segment_index=seg_data.get("index", 0),
                start_time=seg_data.get("start", 0),
                end_time=seg_data.get("end", 0),
                text=seg_data.get("text", ""),
                speaker_label=seg_data.get("speaker"),
            )
            db.add(segment)

        db.commit()
        logger.info(f"Saved transcript for hearing {hearing.id}: {len(result.segments)} segments")

    def _get_audio_duration(self, audio_path: Path) -> Optional[int]:
        """Get audio duration in seconds using ffprobe."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(audio_path)
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return int(float(result.stdout.strip()))
        except Exception:
            pass
        return None


__all__ = ['FLTranscribeStage', 'TranscriptionResult']
