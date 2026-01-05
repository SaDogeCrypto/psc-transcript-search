"""
Load transcripts into SQLite database.
Works with cleaned transcripts from 03_transcribe.py.
"""

import json
import sqlite3
from pathlib import Path

DATA_DIR = Path("data")
TRANSCRIPT_DIR = DATA_DIR / "transcripts"
VIDEO_LIST_PATH = DATA_DIR / "video_list.json"
DB_PATH = DATA_DIR / "psc_transcripts.db"


def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    """Initialize database schema if needed."""
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hearings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            youtube_id VARCHAR(20) UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            hearing_date DATE,
            duration_seconds INTEGER,
            youtube_url TEXT NOT NULL,
            transcript_status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hearing_id INTEGER REFERENCES hearings(id) ON DELETE CASCADE,
            segment_index INTEGER NOT NULL,
            start_time FLOAT NOT NULL,
            end_time FLOAT NOT NULL,
            text TEXT NOT NULL,
            original_text TEXT,
            speaker VARCHAR(100),
            speaker_role VARCHAR(50),
            topics TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(hearing_id, segment_index)
        )
    """)

    # Create FTS virtual table
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
            text,
            content='segments',
            content_rowid='id'
        )
    """)

    conn.commit()


def load_hearing(conn, video: dict) -> int:
    """Insert or update hearing record, return ID."""
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO hearings (youtube_id, title, description, duration_seconds, youtube_url, transcript_status)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (youtube_id) DO UPDATE SET
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            duration_seconds = EXCLUDED.duration_seconds,
            transcript_status = EXCLUDED.transcript_status,
            updated_at = CURRENT_TIMESTAMP
    """, (
        video["youtube_id"],
        video["title"],
        video.get("description", ""),
        video.get("duration_seconds", 0),
        f"https://www.youtube.com/watch?v={video['youtube_id']}",
        "completed"
    ))

    cursor.execute("SELECT id FROM hearings WHERE youtube_id = ?", (video["youtube_id"],))
    hearing_id = cursor.fetchone()[0]

    conn.commit()
    return hearing_id


def load_segments(conn, hearing_id: int, transcript: dict) -> int:
    """Load transcript segments into database."""
    cursor = conn.cursor()

    # Delete existing segments for this hearing
    cursor.execute("DELETE FROM segments WHERE hearing_id = ?", (hearing_id,))

    # Insert segments
    count = 0
    for seg in transcript.get("segments", []):
        text = seg.get("text", "").strip()

        # Skip very short segments
        if len(text.split()) < 3:
            continue

        cursor.execute("""
            INSERT INTO segments (hearing_id, segment_index, start_time, end_time, text, original_text, speaker_role)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            hearing_id,
            seg.get("index", 0),
            seg.get("start", 0),
            seg.get("end", 0),
            text,
            seg.get("original_text"),
            "Unknown"
        ))
        count += 1

    # Rebuild FTS index for this hearing's segments
    cursor.execute("""
        INSERT INTO segments_fts(segments_fts) VALUES('rebuild')
    """)

    conn.commit()
    return count


def main():
    conn = get_connection()
    init_db(conn)

    # Load video metadata
    if not VIDEO_LIST_PATH.exists():
        print(f"Error: {VIDEO_LIST_PATH} not found. Run 01_fetch_videos.py first.")
        return

    with open(VIDEO_LIST_PATH) as f:
        videos = json.load(f)

    print(f"Found {len(videos)} videos in metadata")

    # Load each transcript (prefer cleaned version)
    transcript_files = list(TRANSCRIPT_DIR.glob("*.json"))
    # Build map of video_id -> best transcript file
    transcripts_map = {}
    for f in transcript_files:
        if "_cleaned" in f.stem:
            video_id = f.stem.replace("_cleaned", "")
            transcripts_map[video_id] = f  # Cleaned version takes priority
        elif f.stem not in transcripts_map:
            transcripts_map[f.stem] = f

    print(f"Found {len(transcripts_map)} transcript files")

    total_segments = 0
    for i, (video_id, transcript_path) in enumerate(transcripts_map.items()):

        # Find matching video metadata
        video = next((v for v in videos if v["youtube_id"] == video_id), None)
        if not video:
            # Create minimal metadata
            video = {
                "youtube_id": video_id,
                "title": f"Hearing {video_id}",
                "duration_seconds": 0
            }

        print(f"[{i+1}/{len(transcript_files)}] Loading: {video['title'][:50]}...")

        # Load transcript
        with open(transcript_path) as f:
            transcript = json.load(f)

        # Insert into database
        hearing_id = load_hearing(conn, video)
        segment_count = load_segments(conn, hearing_id, transcript)

        total_segments += segment_count
        cleaned = "cleaned" if transcript.get("cleaned") else "raw"
        print(f"  Loaded {segment_count} segments ({cleaned})")

    conn.close()
    print(f"\nDone! Total: {len(transcript_files)} hearings, {total_segments} segments")


if __name__ == "__main__":
    main()
