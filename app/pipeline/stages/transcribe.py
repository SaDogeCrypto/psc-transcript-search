"""
Transcribe Stage - Transcribes audio using Whisper.

Supports:
- Azure OpenAI Whisper API (if AZURE_OPENAI_ENDPOINT is set)
- OpenAI Whisper API (if OPENAI_API_KEY is set)
- Local whisper model (if USE_OPENAI_WHISPER=false)

Saves transcript to database and creates segments.
"""

import os
import json
import logging
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from sqlalchemy.orm import Session

from app.pipeline.stages.base import BaseStage, StageResult
from app.models.database import Hearing, Transcript, Segment, PipelineJob

logger = logging.getLogger(__name__)

# Configuration
AUDIO_DIR = Path(os.getenv("AUDIO_DIR", "data/audio"))
USE_OPENAI_WHISPER = os.getenv("USE_OPENAI_WHISPER", "true").lower() == "true"
LOCAL_WHISPER_MODEL = os.getenv("LOCAL_WHISPER_MODEL", "medium")  # Local model

# Azure Whisper has 25MB limit - use 24MB to be safe
MAX_FILE_SIZE_BYTES = 24 * 1024 * 1024  # 24MB
CHUNK_DURATION_SECONDS = 600  # 10 minutes per chunk

# Azure OpenAI configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
AZURE_WHISPER_DEPLOYMENT = os.getenv("AZURE_WHISPER_DEPLOYMENT", "whisper")

# OpenAI configuration (fallback if Azure not configured)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")

# Whisper API pricing (as of 2024)
WHISPER_COST_PER_MINUTE = 0.006  # $0.006 per minute


class TranscribeStage(BaseStage):
    """Transcribe audio using Whisper."""

    name = "transcribe"
    in_progress_status = "transcribing"
    complete_status = "transcribed"

    def __init__(self, audio_dir: Optional[Path] = None):
        self.audio_dir = audio_dir or AUDIO_DIR
        self._openai_client = None
        self._local_model = None
        self._use_azure = bool(AZURE_OPENAI_ENDPOINT)

    @property
    def openai_client(self):
        """Lazy load OpenAI client (Azure or standard)."""
        if self._openai_client is None and USE_OPENAI_WHISPER:
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

    @property
    def local_model(self):
        """Lazy load local Whisper model."""
        if self._local_model is None and not USE_OPENAI_WHISPER:
            import whisper
            logger.info(f"Loading local Whisper model: {LOCAL_WHISPER_MODEL}")
            self._local_model = whisper.load_model(LOCAL_WHISPER_MODEL)
        return self._local_model

    def validate(self, hearing: Hearing, db: Session) -> bool:
        """Check if audio file exists."""
        audio_path = self._get_audio_path(hearing)

        if not audio_path.exists():
            logger.warning(f"Audio file not found for hearing {hearing.id}: {audio_path}")
            return False

        # Check if already transcribed
        existing = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()
        if existing:
            logger.info(f"Transcript already exists for hearing {hearing.id}")
            # Still valid - we'll skip

        return True

    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """Transcribe audio file."""
        audio_path = self._get_audio_path(hearing)

        # Check if already transcribed
        existing = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()
        if existing:
            logger.info(f"Using existing transcript for hearing {hearing.id}")
            return StageResult(
                success=True,
                output={"transcript_id": existing.id, "skipped": True},
                cost_usd=0.0
            )

        try:
            # Transcribe using appropriate method
            if USE_OPENAI_WHISPER:
                result = self._transcribe_openai(audio_path, hearing)
            else:
                result = self._transcribe_local(audio_path, hearing)

            if not result["success"]:
                return StageResult(
                    success=False,
                    error=result.get("error", "Transcription failed"),
                    should_retry=True
                )

            # Save transcript and segments to database
            transcript = self._save_transcript(hearing, result, db)

            return StageResult(
                success=True,
                output={
                    "transcript_id": transcript.id,
                    "word_count": transcript.word_count,
                    "segment_count": len(result.get("segments", [])),
                },
                cost_usd=result.get("cost_usd", 0.0)
            )

        except Exception as e:
            logger.exception(f"Transcription error for hearing {hearing.id}")
            return StageResult(
                success=False,
                error=f"Transcription error: {str(e)}",
                should_retry=True
            )

    def _get_audio_path(self, hearing: Hearing) -> Path:
        """Get the audio file path for a hearing."""
        filename = hearing.external_id or f"hearing_{hearing.id}"
        filename = "".join(c for c in filename if c.isalnum() or c in "-_")
        return self.audio_dir / f"{filename}.mp3"

    def _needs_chunking(self, audio_path: Path) -> bool:
        """Check if audio file exceeds size limit and needs chunking."""
        file_size = audio_path.stat().st_size
        return file_size > MAX_FILE_SIZE_BYTES

    def _split_audio(self, audio_path: Path) -> List[Tuple[Path, float]]:
        """Split audio into chunks using ffmpeg.

        Returns list of (chunk_path, start_time_offset) tuples.
        """
        duration = self._get_audio_duration(audio_path) or 0
        if duration == 0:
            raise ValueError(f"Could not determine duration of {audio_path}")

        chunks = []
        temp_dir = tempfile.mkdtemp(prefix="whisper_chunks_")

        # Calculate number of chunks needed
        num_chunks = (duration // CHUNK_DURATION_SECONDS) + 1
        logger.info(f"Splitting {audio_path.name} ({duration}s) into {num_chunks} chunks")

        for i in range(int(num_chunks)):
            start_time = i * CHUNK_DURATION_SECONDS
            chunk_path = Path(temp_dir) / f"chunk_{i:03d}.mp3"

            try:
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-y",  # Overwrite output
                        "-i", str(audio_path),
                        "-ss", str(start_time),
                        "-t", str(CHUNK_DURATION_SECONDS),
                        "-c:a", "libmp3lame",
                        "-q:a", "4",  # Good quality
                        str(chunk_path)
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120
                )

                if result.returncode == 0 and chunk_path.exists() and chunk_path.stat().st_size > 0:
                    chunks.append((chunk_path, float(start_time)))
                    logger.debug(f"Created chunk {i}: {chunk_path.name} (offset={start_time}s)")
                else:
                    logger.warning(f"Failed to create chunk {i}: {result.stderr}")

            except subprocess.TimeoutExpired:
                logger.error(f"Timeout creating chunk {i}")
                continue
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

    def _transcribe_openai(self, audio_path: Path, hearing: Hearing) -> dict:
        """Transcribe using OpenAI/Azure Whisper API."""
        # Check if file needs chunking
        if self._needs_chunking(audio_path):
            return self._transcribe_chunked(audio_path, hearing)

        return self._transcribe_single_file(audio_path, hearing)

    def _transcribe_single_file(self, audio_path: Path, hearing: Hearing) -> dict:
        """Transcribe a single audio file (under size limit)."""
        # Use Azure deployment name or OpenAI model name
        model_name = AZURE_WHISPER_DEPLOYMENT if self._use_azure else WHISPER_MODEL
        provider = "Azure OpenAI" if self._use_azure else "OpenAI"

        logger.info(f"Transcribing with {provider} Whisper ({model_name}): {audio_path}")

        # Get audio duration for cost calculation
        duration_seconds = hearing.duration_seconds or self._get_audio_duration(audio_path)
        duration_minutes = (duration_seconds or 0) / 60

        try:
            with open(audio_path, "rb") as audio_file:
                response = self.openai_client.audio.transcriptions.create(
                    model=model_name,
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )

            # Parse response
            full_text = response.text
            segments = []

            if hasattr(response, 'segments') and response.segments:
                for i, seg in enumerate(response.segments):
                    # Handle both dict and object responses
                    if isinstance(seg, dict):
                        segments.append({
                            "index": i,
                            "start": seg.get("start", 0),
                            "end": seg.get("end", 0),
                            "text": seg.get("text", "").strip(),
                        })
                    else:
                        # Object with attributes (Azure OpenAI response)
                        segments.append({
                            "index": i,
                            "start": getattr(seg, "start", 0),
                            "end": getattr(seg, "end", 0),
                            "text": getattr(seg, "text", "").strip(),
                        })

            cost_usd = duration_minutes * WHISPER_COST_PER_MINUTE

            logger.info(f"{provider} transcription complete: {len(segments)} segments, ${cost_usd:.4f}")

            return {
                "success": True,
                "text": full_text,
                "segments": segments,
                "model": model_name,
                "cost_usd": cost_usd,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _transcribe_chunked(self, audio_path: Path, hearing: Hearing) -> dict:
        """Transcribe large audio file by splitting into chunks."""
        model_name = AZURE_WHISPER_DEPLOYMENT if self._use_azure else WHISPER_MODEL
        provider = "Azure OpenAI" if self._use_azure else "OpenAI"

        file_size_mb = audio_path.stat().st_size / (1024 * 1024)
        logger.info(f"File {audio_path.name} is {file_size_mb:.1f}MB - splitting into chunks")

        # Get total duration for cost calculation
        duration_seconds = hearing.duration_seconds or self._get_audio_duration(audio_path)
        duration_minutes = (duration_seconds or 0) / 60

        chunks = []
        try:
            # Split audio into chunks
            chunks = self._split_audio(audio_path)
            logger.info(f"Created {len(chunks)} chunks for {audio_path.name}")

            # Transcribe each chunk
            all_segments = []
            all_text_parts = []
            segment_index = 0

            for chunk_path, time_offset in chunks:
                logger.info(f"Transcribing chunk: {chunk_path.name} (offset={time_offset}s)")

                try:
                    with open(chunk_path, "rb") as audio_file:
                        response = self.openai_client.audio.transcriptions.create(
                            model=model_name,
                            file=audio_file,
                            response_format="verbose_json",
                            timestamp_granularities=["segment"]
                        )

                    # Add text
                    if response.text:
                        all_text_parts.append(response.text)

                    # Process segments with time offset adjustment
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

                            # Adjust timestamps by chunk offset
                            all_segments.append({
                                "index": segment_index,
                                "start": start + time_offset,
                                "end": end + time_offset,
                                "text": text,
                            })
                            segment_index += 1

                    logger.debug(f"Chunk {chunk_path.name}: {len(response.segments) if hasattr(response, 'segments') else 0} segments")

                except Exception as e:
                    logger.error(f"Error transcribing chunk {chunk_path.name}: {e}")
                    # Continue with other chunks rather than failing entirely
                    continue

            if not all_segments:
                return {"success": False, "error": "No segments transcribed from any chunk"}

            # Merge all text
            full_text = " ".join(all_text_parts)
            cost_usd = duration_minutes * WHISPER_COST_PER_MINUTE

            logger.info(f"{provider} chunked transcription complete: {len(all_segments)} segments, ${cost_usd:.4f}")

            return {
                "success": True,
                "text": full_text,
                "segments": all_segments,
                "model": model_name,
                "cost_usd": cost_usd,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

        finally:
            # Clean up chunk files
            self._cleanup_chunks(chunks)

    def _transcribe_local(self, audio_path: Path, hearing: Hearing) -> dict:
        """Transcribe using local Whisper model."""
        logger.info(f"Transcribing with local Whisper ({LOCAL_WHISPER_MODEL}): {audio_path}")

        try:
            result = self.local_model.transcribe(
                str(audio_path),
                language="en",
                verbose=False,
                word_timestamps=False
            )

            segments = []
            for i, seg in enumerate(result.get("segments", [])):
                segments.append({
                    "index": i,
                    "start": seg.get("start", 0),
                    "end": seg.get("end", 0),
                    "text": seg.get("text", "").strip(),
                })

            logger.info(f"Local transcription complete: {len(segments)} segments")

            return {
                "success": True,
                "text": result.get("text", ""),
                "segments": segments,
                "model": f"whisper-local-{LOCAL_WHISPER_MODEL}",
                "cost_usd": 0.0,  # Local is free
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _save_transcript(self, hearing: Hearing, result: dict, db: Session) -> Transcript:
        """Save transcript and segments to database."""
        full_text = result.get("text", "")
        segments_data = result.get("segments", [])

        # Create transcript record
        transcript = Transcript(
            hearing_id=hearing.id,
            full_text=full_text,
            word_count=len(full_text.split()),
            model=result.get("model"),
            cost_usd=result.get("cost_usd", 0.0),
        )
        db.add(transcript)
        db.flush()  # Get the ID

        # Create segment records
        for seg_data in segments_data:
            segment = Segment(
                hearing_id=hearing.id,
                transcript_id=transcript.id,
                segment_index=seg_data.get("index", 0),
                start_time=seg_data.get("start", 0),
                end_time=seg_data.get("end", 0),
                text=seg_data.get("text", ""),
                speaker=seg_data.get("speaker"),
                speaker_role=seg_data.get("speaker_role"),
            )
            db.add(segment)

        db.commit()
        logger.info(f"Saved transcript {transcript.id} with {len(segments_data)} segments")

        return transcript

    def _get_audio_duration(self, audio_path: Path) -> Optional[int]:
        """Get audio duration in seconds using ffprobe."""
        try:
            import subprocess
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

    def on_error(self, hearing: Hearing, job: PipelineJob, result: StageResult, db: Session):
        """Clean up partial transcript on error."""
        # Remove any partial transcript
        transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()
        if transcript:
            # Also removes segments via cascade
            db.delete(transcript)
            db.commit()
            logger.info(f"Cleaned up partial transcript for hearing {hearing.id}")
