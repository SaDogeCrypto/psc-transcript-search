"""
Transcribe audio files using OpenAI Whisper.
Outputs JSON with timestamps for each segment.
Automatically cleans transcripts using PSC-specific rules.
"""

import json
import whisper
from pathlib import Path
from datetime import datetime

# Import the cleaner
from psc_transcript_cleaner import clean_transcript_text

DATA_DIR = Path("data")
AUDIO_DIR = DATA_DIR / "audio"
TRANSCRIPT_DIR = DATA_DIR / "transcripts"

# Use "medium" for good balance of speed/accuracy
# Use "large-v3" for best accuracy (slower)
MODEL_SIZE = "medium"


def transcribe_audio(audio_path: Path, model, apply_cleaning: bool = True) -> dict:
    """Transcribe audio file and return segments with timestamps."""
    result = model.transcribe(
        str(audio_path),
        language="en",
        verbose=False,
        word_timestamps=False  # Segment-level is enough
    )

    segments = []
    for i, seg in enumerate(result["segments"]):
        raw_text = seg["text"].strip()
        cleaned_text = clean_transcript_text(raw_text) if apply_cleaning else raw_text

        segments.append({
            "index": i,
            "start": seg["start"],
            "end": seg["end"],
            "text": cleaned_text,
            "original_text": raw_text if apply_cleaning else None
        })

    full_text = result["text"]
    if apply_cleaning:
        full_text = clean_transcript_text(full_text)

    return {
        "text": full_text,
        "segments": segments,
        "language": result.get("language", "en"),
        "cleaned": apply_cleaning
    }


def main():
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Loading Whisper model: {MODEL_SIZE}")
    model = whisper.load_model(MODEL_SIZE)
    print("PSC transcript cleaning: ENABLED")

    audio_files = list(AUDIO_DIR.glob("*.mp3"))
    print(f"Found {len(audio_files)} audio files to transcribe")

    for i, audio_path in enumerate(audio_files):
        video_id = audio_path.stem
        output_path = TRANSCRIPT_DIR / f"{video_id}.json"

        if output_path.exists():
            print(f"[{i+1}/{len(audio_files)}] Already transcribed: {video_id}")
            continue

        print(f"[{i+1}/{len(audio_files)}] Transcribing: {video_id}")
        start_time = datetime.now()

        try:
            result = transcribe_audio(audio_path, model, apply_cleaning=True)

            # Save transcript
            with open(output_path, "w") as f:
                json.dump(result, f, indent=2)

            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"  Done in {elapsed:.1f}s ({len(result['segments'])} segments, cleaned)")

        except Exception as e:
            print(f"  Error transcribing {video_id}: {e}")
            continue

    print("All transcriptions complete!")


if __name__ == "__main__":
    main()
