"""
Process transcript segments:
1. Extract topics using LLM
2. Attempt speaker identification
3. Generate embeddings for semantic search
"""

import json
import os
from pathlib import Path
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
PROCESSED_DIR = DATA_DIR / "processed"

client = OpenAI()  # Uses OPENAI_API_KEY env var

# Known speakers to help with identification
KNOWN_SPEAKERS = {
    "commissioners": ["Jason Shaw", "Tim Echols", "Fitz Johnson", "Lauren McDonald", "Tricia Pridemore"],
    "staff": ["Robert Trokey"],
    "georgia_power": ["Georgia Power", "the company"],
    "intervenors": ["SELC", "Sierra Club", "Georgia Watch"]
}

TOPIC_EXTRACTION_PROMPT = """Analyze this transcript segment from a Georgia Public Service Commission hearing about electric utility regulation.

Extract:
1. Main topics discussed (e.g., "load forecast", "data center demand", "solar capacity", "rate impact")
2. If identifiable, who is speaking (Commissioner, Georgia Power witness, PSC Staff, Intervenor)
3. Any specific numbers, dates, or commitments mentioned

Segment text:
{text}

Respond in JSON format:
{{
    "topics": ["topic1", "topic2"],
    "speaker_role": "Commissioner|Utility Witness|PSC Staff|Intervenor|Unknown",
    "speaker_name": "Name if identifiable, null otherwise",
    "key_facts": ["any specific numbers or commitments"]
}}"""


def extract_topics(text: str) -> dict:
    """Use GPT-4o-mini to extract topics and speaker info."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are an expert at analyzing regulatory hearing transcripts."},
                {"role": "user", "content": TOPIC_EXTRACTION_PROMPT.format(text=text)}
            ],
            response_format={"type": "json_object"},
            max_tokens=200
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"  Error extracting topics: {e}")
        return {"topics": [], "speaker_role": "Unknown", "speaker_name": None, "key_facts": []}


def generate_embedding(text: str) -> list[float]:
    """Generate embedding for semantic search."""
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


def process_transcript(video_id: str, transcript: dict) -> list[dict]:
    """Process all segments in a transcript."""
    processed_segments = []

    for i, seg in enumerate(transcript["segments"]):
        # Skip very short segments
        if len(seg["text"].split()) < 5:
            continue

        print(f"    Processing segment {i+1}/{len(transcript['segments'])}", end="\r")

        # Extract topics (batch this for efficiency in production)
        extracted = extract_topics(seg["text"])

        # Generate embedding
        embedding = generate_embedding(seg["text"])

        processed_segments.append({
            "video_id": video_id,
            "segment_index": seg["index"],
            "start_time": seg["start"],
            "end_time": seg["end"],
            "text": seg["text"],
            "speaker": extracted.get("speaker_name"),
            "speaker_role": extracted.get("speaker_role", "Unknown"),
            "topics": extracted.get("topics", []),
            "key_facts": extracted.get("key_facts", []),
            "embedding": embedding
        })

    print()  # New line after progress
    return processed_segments


def main():
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    transcript_files = list(TRANSCRIPT_DIR.glob("*.json"))
    print(f"Processing {len(transcript_files)} transcripts...")

    for i, transcript_path in enumerate(transcript_files):
        video_id = transcript_path.stem
        output_path = PROCESSED_DIR / f"{video_id}.json"

        if output_path.exists():
            print(f"[{i+1}/{len(transcript_files)}] Already processed: {video_id}")
            continue

        print(f"[{i+1}/{len(transcript_files)}] Processing: {video_id}")

        with open(transcript_path) as f:
            transcript = json.load(f)

        processed = process_transcript(video_id, transcript)

        with open(output_path, "w") as f:
            json.dump(processed, f, indent=2)

        print(f"  Processed {len(processed)} segments")

    print("Done!")


if __name__ == "__main__":
    main()
