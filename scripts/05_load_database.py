"""
Load processed segments into PostgreSQL database.
"""

import json
import os
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
PROCESSED_DIR = DATA_DIR / "processed"
VIDEO_LIST_PATH = DATA_DIR / "video_list.json"

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/psc_transcripts")


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def load_hearings(conn, videos: list[dict]):
    """Insert hearing records."""
    cursor = conn.cursor()

    for video in videos:
        cursor.execute("""
            INSERT INTO hearings (youtube_id, title, duration_seconds, youtube_url, transcript_status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (youtube_id) DO UPDATE SET
                title = EXCLUDED.title,
                duration_seconds = EXCLUDED.duration_seconds
            RETURNING id
        """, (
            video["youtube_id"],
            video["title"],
            video.get("duration_seconds", 0),
            f"https://www.youtube.com/watch?v={video['youtube_id']}",
            "completed"
        ))

    conn.commit()
    cursor.close()


def load_segments(conn, video_id: str, segments: list[dict]):
    """Insert segment records with embeddings."""
    cursor = conn.cursor()

    # Get hearing ID
    cursor.execute("SELECT id FROM hearings WHERE youtube_id = %s", (video_id,))
    result = cursor.fetchone()
    if not result:
        print(f"  Warning: No hearing found for {video_id}")
        return

    hearing_id = result[0]

    # Prepare data for bulk insert
    values = [
        (
            hearing_id,
            seg["segment_index"],
            seg["start_time"],
            seg["end_time"],
            seg["text"],
            seg.get("speaker"),
            seg.get("speaker_role", "Unknown"),
            seg.get("topics", []),
            seg["embedding"]
        )
        for seg in segments
    ]

    execute_values(cursor, """
        INSERT INTO segments (hearing_id, segment_index, start_time, end_time, text, speaker, speaker_role, topics, embedding)
        VALUES %s
        ON CONFLICT (hearing_id, segment_index) DO UPDATE SET
            text = EXCLUDED.text,
            speaker = EXCLUDED.speaker,
            speaker_role = EXCLUDED.speaker_role,
            topics = EXCLUDED.topics,
            embedding = EXCLUDED.embedding
    """, values)

    conn.commit()
    cursor.close()


def main():
    conn = get_connection()

    # Load video metadata
    with open(VIDEO_LIST_PATH) as f:
        videos = json.load(f)

    print(f"Loading {len(videos)} hearings...")
    load_hearings(conn, videos)

    # Load segments
    processed_files = list(PROCESSED_DIR.glob("*.json"))
    print(f"Loading segments from {len(processed_files)} files...")

    for i, processed_path in enumerate(processed_files):
        video_id = processed_path.stem
        print(f"[{i+1}/{len(processed_files)}] Loading: {video_id}")

        with open(processed_path) as f:
            segments = json.load(f)

        load_segments(conn, video_id, segments)
        print(f"  Loaded {len(segments)} segments")

    conn.close()
    print("Done!")


if __name__ == "__main__":
    main()
