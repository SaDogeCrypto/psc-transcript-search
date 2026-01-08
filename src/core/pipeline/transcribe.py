"""
Transcribe stage - Whisper transcription for hearing audio.

Supports multiple Whisper providers (in priority order):
1. Groq (fastest, cheapest)
2. Azure OpenAI
3. OpenAI

Handles:
- Large file chunking (files > 24MB)
- Speaker context prompts per state
- Segment creation with timestamps
"""

import os
import logging
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any

from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.models.hearing import Hearing
from src.core.models.transcript import TranscriptSegment
from src.core.pipeline.base import PipelineStage, StageResult

logger = logging.getLogger(__name__)
settings = get_settings()

# File size limits
MAX_FILE_SIZE_BYTES = 24 * 1024 * 1024  # 24MB (Groq limit is 25MB)
CHUNK_DURATION_SECONDS = 600  # 10 minutes per chunk

# Pricing per minute
WHISPER_COST_PER_MINUTE = 0.006  # OpenAI/Azure
GROQ_WHISPER_COST_PER_MINUTE = 0.04 / 60  # $0.04/hour

# State-specific context prompts for better transcription accuracy
STATE_PROMPTS = {
    "FL": (
        "Florida Public Service Commission hearing transcript. "
        "FPSC, Florida Power & Light, FPL, Duke Energy Florida, Tampa Electric, TECO, "
        "NextEra, Gulf Power, JEA. Chairman Fay, Commissioner Clark, Commissioner La Rosa, "
        "Commissioner Passidomo, Commissioner Graham. "
        "Docket numbers like 20250035-GU, 20240001-EI."
    ),
    "TX": (
        "Public Utility Commission of Texas hearing transcript. "
        "PUCT, ERCOT, Oncor, CenterPoint Energy, AEP Texas, Texas-New Mexico Power. "
        "Docket numbers like 12345."
    ),
    "CA": (
        "California Public Utilities Commission hearing transcript. "
        "CPUC, PG&E, Pacific Gas and Electric, SCE, Southern California Edison, "
        "SDG&E, San Diego Gas & Electric. "
        "Application numbers like A.XX-XX-XXX, Rulemaking numbers like R.XX-XX-XXX."
    ),
}


class TranscribeStage(PipelineStage[Hearing]):
    """
    Transcribe hearing audio using Whisper.

    Automatically selects the best available provider (Groq > Azure > OpenAI).
    Handles large files by chunking with ffmpeg.
    """

    name = "transcribe"

    def __init__(self, audio_dir: Optional[Path] = None):
        self.audio_dir = Path(audio_dir or settings.audio_dir)
        self._groq_client = None
        self._openai_client = None
        self.provider = settings.whisper_provider

    @property
    def groq_client(self):
        """Lazy load Groq client."""
        if self._groq_client is None and self.provider == "groq":
            from groq import Groq
            self._groq_client = Groq(api_key=settings.groq_api_key)
            logger.info("Using Groq Whisper API")
        return self._groq_client

    @property
    def openai_client(self):
        """Lazy load OpenAI/Azure client."""
        if self._openai_client is None and self.provider in ("azure", "openai"):
            if self.provider == "azure":
                from openai import AzureOpenAI
                self._openai_client = AzureOpenAI(
                    azure_endpoint=settings.azure_openai_endpoint,
                    api_key=settings.azure_openai_api_key,
                    api_version=settings.azure_openai_api_version,
                )
                logger.info(f"Using Azure OpenAI Whisper: {settings.azure_openai_endpoint}")
            else:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=settings.openai_api_key)
                logger.info("Using OpenAI Whisper API")
        return self._openai_client

    def validate(self, hearing: Hearing, db: Session) -> Tuple[bool, str]:
        """Check if hearing can be transcribed."""
        if self.provider == "none":
            return False, "No Whisper API configured"

        audio_path = self._get_audio_path(hearing)
        if not audio_path or not audio_path.exists():
            return False, f"Audio file not found: {audio_path}"

        # Check if already transcribed
        segment_count = db.query(TranscriptSegment).filter(
            TranscriptSegment.hearing_id == hearing.id
        ).count()
        if segment_count > 0:
            return False, f"Already transcribed ({segment_count} segments)"

        return True, ""

    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """Transcribe audio and save segments."""
        audio_path = self._get_audio_path(hearing)

        if not audio_path or not audio_path.exists():
            return StageResult(success=False, error=f"Audio file not found: {audio_path}")

        try:
            # Build context prompt for this state
            initial_prompt = self._build_prompt(hearing)

            # Transcribe
            if self._needs_chunking(audio_path):
                text, segments, cost = self._transcribe_chunked(audio_path, hearing, initial_prompt)
            elif self.provider == "groq":
                text, segments, cost = self._transcribe_groq(audio_path, hearing, initial_prompt)
            else:
                text, segments, cost = self._transcribe_openai(audio_path, hearing, initial_prompt)

            # Save to database
            self._save_transcript(hearing, text, segments, cost, db)

            return StageResult(
                success=True,
                data={
                    "segments": len(segments),
                    "words": hearing.word_count,
                    "duration_minutes": hearing.duration_minutes,
                },
                cost_usd=cost,
                model=self._get_model_name(),
            )

        except Exception as e:
            logger.exception(f"Transcription error for hearing {hearing.id}")
            return StageResult(success=False, error=str(e))

    def _get_audio_path(self, hearing: Hearing) -> Optional[Path]:
        """Find audio file for hearing."""
        # Try external_id first, then hearing id
        filename = hearing.external_id or f"hearing_{hearing.id}"
        # Sanitize filename
        filename = "".join(c for c in filename if c.isalnum() or c in "-_")

        # Check common extensions
        for ext in [".mp3", ".m4a", ".wav", ".mp4"]:
            path = self.audio_dir / f"{filename}{ext}"
            if path.exists():
                return path

        # Check state-specific subdirectory
        if hearing.state_code:
            state_dir = self.audio_dir / hearing.state_code.lower()
            if state_dir.exists():
                for ext in [".mp3", ".m4a", ".wav", ".mp4"]:
                    path = state_dir / f"{filename}{ext}"
                    if path.exists():
                        return path

        return None

    def _build_prompt(self, hearing: Hearing) -> str:
        """Build Whisper initial_prompt with state context."""
        base_prompt = STATE_PROMPTS.get(
            hearing.state_code,
            "Public utility commission hearing transcript."
        )

        if hearing.title:
            base_prompt += f" Hearing: {hearing.title[:200]}"

        return base_prompt

    def _get_model_name(self) -> str:
        """Get the model name for the current provider."""
        if self.provider == "groq":
            return settings.groq_whisper_model
        elif self.provider == "azure":
            return settings.azure_whisper_deployment
        return settings.whisper_model

    def _needs_chunking(self, audio_path: Path) -> bool:
        """Check if audio exceeds size limit."""
        return audio_path.stat().st_size > MAX_FILE_SIZE_BYTES

    def _transcribe_groq(
        self,
        audio_path: Path,
        hearing: Hearing,
        initial_prompt: str
    ) -> Tuple[str, List[Dict], float]:
        """Transcribe using Groq Whisper API."""
        logger.info(f"Transcribing with Groq Whisper: {audio_path.name}")

        duration_seconds = hearing.duration_seconds or self._get_audio_duration(audio_path)
        duration_minutes = (duration_seconds or 0) / 60

        with open(audio_path, "rb") as audio_file:
            response = self.groq_client.audio.transcriptions.create(
                model=settings.groq_whisper_model,
                file=audio_file,
                response_format="verbose_json",
                prompt=initial_prompt if initial_prompt else None,
            )

        full_text = response.text
        segments = self._parse_segments(response)
        cost_usd = duration_minutes * GROQ_WHISPER_COST_PER_MINUTE

        logger.info(f"Groq transcription complete: {len(segments)} segments, {duration_minutes:.1f} min")
        return full_text, segments, cost_usd

    def _transcribe_openai(
        self,
        audio_path: Path,
        hearing: Hearing,
        initial_prompt: str
    ) -> Tuple[str, List[Dict], float]:
        """Transcribe using OpenAI/Azure Whisper API."""
        provider = "Azure OpenAI" if self.provider == "azure" else "OpenAI"
        model_name = self._get_model_name()

        logger.info(f"Transcribing with {provider} Whisper: {audio_path.name}")

        duration_seconds = hearing.duration_seconds or self._get_audio_duration(audio_path)
        duration_minutes = (duration_seconds or 0) / 60

        with open(audio_path, "rb") as audio_file:
            response = self.openai_client.audio.transcriptions.create(
                model=model_name,
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
                prompt=initial_prompt if initial_prompt else None,
            )

        full_text = response.text
        segments = self._parse_segments(response)
        cost_usd = duration_minutes * WHISPER_COST_PER_MINUTE

        logger.info(f"{provider} transcription complete: {len(segments)} segments, ${cost_usd:.4f}")
        return full_text, segments, cost_usd

    def _transcribe_chunked(
        self,
        audio_path: Path,
        hearing: Hearing,
        initial_prompt: str
    ) -> Tuple[str, List[Dict], float]:
        """Transcribe large audio by splitting into chunks."""
        file_size_mb = audio_path.stat().st_size / (1024 * 1024)
        logger.info(f"File {audio_path.name} is {file_size_mb:.1f}MB - splitting into chunks")

        duration_seconds = hearing.duration_seconds or self._get_audio_duration(audio_path) or 0
        duration_minutes = duration_seconds / 60

        chunks = []
        try:
            chunks = self._split_audio(audio_path, duration_seconds)
            logger.info(f"Created {len(chunks)} chunks")

            all_segments = []
            all_text_parts = []
            segment_index = 0

            for chunk_path, time_offset in chunks:
                logger.info(f"Transcribing chunk: {chunk_path.name} (offset={time_offset}s)")

                try:
                    with open(chunk_path, "rb") as audio_file:
                        if self.provider == "groq":
                            response = self.groq_client.audio.transcriptions.create(
                                model=settings.groq_whisper_model,
                                file=audio_file,
                                response_format="verbose_json",
                                prompt=initial_prompt if initial_prompt else None,
                            )
                        else:
                            response = self.openai_client.audio.transcriptions.create(
                                model=self._get_model_name(),
                                file=audio_file,
                                response_format="verbose_json",
                                timestamp_granularities=["segment"],
                                prompt=initial_prompt if initial_prompt else None,
                            )

                    if response.text:
                        all_text_parts.append(response.text)

                    # Adjust segment timestamps with offset
                    chunk_segments = self._parse_segments(response)
                    for seg in chunk_segments:
                        seg["index"] = segment_index
                        seg["start"] += time_offset
                        seg["end"] += time_offset
                        all_segments.append(seg)
                        segment_index += 1

                except Exception as e:
                    logger.error(f"Error transcribing chunk {chunk_path.name}: {e}")
                    continue

            if not all_segments:
                raise ValueError("No segments transcribed from chunks")

            full_text = " ".join(all_text_parts)

            # Calculate cost based on provider
            if self.provider == "groq":
                cost_usd = duration_minutes * GROQ_WHISPER_COST_PER_MINUTE
            else:
                cost_usd = duration_minutes * WHISPER_COST_PER_MINUTE

            logger.info(f"Chunked transcription complete: {len(all_segments)} segments")
            return full_text, all_segments, cost_usd

        finally:
            self._cleanup_chunks(chunks)

    def _parse_segments(self, response: Any) -> List[Dict]:
        """Parse segments from Whisper response."""
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

        return segments

    def _split_audio(self, audio_path: Path, duration: float) -> List[Tuple[Path, float]]:
        """Split audio into chunks using ffmpeg."""
        if duration == 0:
            duration = self._get_audio_duration(audio_path) or 0
            if duration == 0:
                raise ValueError(f"Could not determine duration of {audio_path}")

        chunks = []
        temp_dir = tempfile.mkdtemp(prefix="whisper_chunks_")
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

    def _save_transcript(
        self,
        hearing: Hearing,
        text: str,
        segments: List[Dict],
        cost: float,
        db: Session
    ):
        """Save transcript to database."""
        # Update hearing
        hearing.full_text = text
        hearing.word_count = len(text.split()) if text else 0
        hearing.whisper_model = self._get_model_name()
        hearing.processing_cost_usd = (hearing.processing_cost_usd or 0) + cost
        hearing.transcript_status = "transcribed"
        hearing.processed_at = datetime.utcnow()

        # Create segment records
        for seg_data in segments:
            segment = TranscriptSegment(
                hearing_id=hearing.id,
                segment_index=seg_data.get("index", 0),
                start_time=seg_data.get("start", 0),
                end_time=seg_data.get("end", 0),
                text=seg_data.get("text", ""),
                speaker_label=seg_data.get("speaker"),
            )
            db.add(segment)

        db.commit()
        logger.info(f"Saved transcript for hearing {hearing.id}: {len(segments)} segments")
