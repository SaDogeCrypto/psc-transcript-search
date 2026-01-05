"""
SQLite database for local testing (no Docker/PostgreSQL required).
"""

import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent.parent / "data" / "psc_transcripts.db"


def dict_factory(cursor, row):
    """Convert SQLite rows to dictionaries."""
    fields = [column[0] for column in cursor.description]
    return {key: value for key, value in zip(fields, row)}


def get_connection():
    """Create a new database connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = dict_factory
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    """Initialize the SQLite database schema."""
    conn = get_connection()
    cursor = conn.cursor()

    # Create hearings table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS hearings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            youtube_id VARCHAR(20) UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            hearing_date DATE,
            duration_seconds INTEGER,
            docket_numbers TEXT,
            youtube_url TEXT NOT NULL,
            audio_path TEXT,
            transcript_status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create segments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hearing_id INTEGER REFERENCES hearings(id) ON DELETE CASCADE,
            segment_index INTEGER NOT NULL,
            start_time FLOAT NOT NULL,
            end_time FLOAT NOT NULL,
            text TEXT NOT NULL,
            speaker VARCHAR(100),
            speaker_role VARCHAR(50),
            topics TEXT,
            embedding TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(hearing_id, segment_index)
        )
    """)

    # Create FTS virtual table for full-text search
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
            text,
            content='segments',
            content_rowid='id'
        )
    """)

    # Triggers to keep FTS in sync
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS segments_ai AFTER INSERT ON segments BEGIN
            INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
        END
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS segments_ad AFTER DELETE ON segments BEGIN
            INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.id, old.text);
        END
    """)

    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS segments_au AFTER UPDATE ON segments BEGIN
            INSERT INTO segments_fts(segments_fts, rowid, text) VALUES('delete', old.id, old.text);
            INSERT INTO segments_fts(rowid, text) VALUES (new.id, new.text);
        END
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")


def add_sample_data():
    """Add sample data for testing."""
    conn = get_connection()
    cursor = conn.cursor()

    # Check if we already have data
    cursor.execute("SELECT COUNT(*) as count FROM hearings")
    if cursor.fetchone()["count"] > 0:
        print("Sample data already exists")
        conn.close()
        return

    # Add sample hearings
    sample_hearings = [
        {
            "youtube_id": "abc123xyz",
            "title": "Georgia Power IRP Hearing - December 10, 2025 (Day 1)",
            "description": "Georgia Public Service Commission hearing on Georgia Power's Integrated Resource Plan and capacity additions.",
            "duration_seconds": 14400,
            "youtube_url": "https://www.youtube.com/watch?v=abc123xyz",
            "transcript_status": "completed"
        },
        {
            "youtube_id": "def456uvw",
            "title": "Georgia Power IRP Hearing - December 11, 2025 (Day 2)",
            "description": "Continuation of capacity hearing focusing on data center load forecasts.",
            "duration_seconds": 18000,
            "youtube_url": "https://www.youtube.com/watch?v=def456uvw",
            "transcript_status": "completed"
        }
    ]

    for hearing in sample_hearings:
        cursor.execute("""
            INSERT INTO hearings (youtube_id, title, description, duration_seconds, youtube_url, transcript_status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            hearing["youtube_id"],
            hearing["title"],
            hearing["description"],
            hearing["duration_seconds"],
            hearing["youtube_url"],
            hearing["transcript_status"]
        ))

    # Add sample segments
    sample_segments = [
        # Hearing 1 segments
        {"hearing_id": 1, "segment_index": 0, "start_time": 0.0, "end_time": 30.0,
         "text": "Good morning everyone. We're here today to discuss Georgia Power's Integrated Resource Plan and the proposed capacity additions for the 2029-2031 planning period.",
         "speaker": "Chairman Jason Shaw", "speaker_role": "Commissioner", "topics": json.dumps(["IRP", "capacity planning"])},

        {"hearing_id": 1, "segment_index": 1, "start_time": 30.0, "end_time": 65.0,
         "text": "The company is proposing significant additions to meet the growing demand, particularly from data centers. We've seen unprecedented load growth in the region.",
         "speaker": "Georgia Power Witness", "speaker_role": "Utility Witness", "topics": json.dumps(["data center", "load growth"])},

        {"hearing_id": 1, "segment_index": 2, "start_time": 65.0, "end_time": 120.0,
         "text": "Our load forecast shows an increase of approximately 9000 megawatts over the next five years, driven primarily by data center development in the metro Atlanta area.",
         "speaker": "Georgia Power Witness", "speaker_role": "Utility Witness", "topics": json.dumps(["load forecast", "9000 megawatts", "data center"])},

        {"hearing_id": 1, "segment_index": 3, "start_time": 120.0, "end_time": 180.0,
         "text": "Commissioner Echols, do you have questions for the witness regarding the solar capacity additions proposed in this filing?",
         "speaker": "Chairman Jason Shaw", "speaker_role": "Commissioner", "topics": json.dumps(["solar capacity"])},

        {"hearing_id": 1, "segment_index": 4, "start_time": 180.0, "end_time": 240.0,
         "text": "Yes, thank you Chairman. I'd like to understand the rate impact on residential customers. What is the expected monthly bill increase for the average residential customer?",
         "speaker": "Commissioner Tim Echols", "speaker_role": "Commissioner", "topics": json.dumps(["rate impact", "residential customers"])},

        {"hearing_id": 1, "segment_index": 5, "start_time": 240.0, "end_time": 300.0,
         "text": "Based on our analysis, the average residential customer would see an increase of approximately $12 to $15 per month once these capacity additions are fully operational.",
         "speaker": "Georgia Power Witness", "speaker_role": "Utility Witness", "topics": json.dumps(["rate impact", "residential customers", "bill increase"])},

        # Hearing 2 segments
        {"hearing_id": 2, "segment_index": 0, "start_time": 0.0, "end_time": 45.0,
         "text": "We're reconvening the capacity hearing. Today we'll focus on the coal plant retirement schedule and the transition to renewable energy sources.",
         "speaker": "Chairman Jason Shaw", "speaker_role": "Commissioner", "topics": json.dumps(["coal plant retirement", "renewable energy"])},

        {"hearing_id": 2, "segment_index": 1, "start_time": 45.0, "end_time": 100.0,
         "text": "The Sierra Club has filed comments expressing concern about the pace of coal retirement. We believe Georgia Power should accelerate the closure of Plant Scherer.",
         "speaker": "SELC Representative", "speaker_role": "Intervenor", "topics": json.dumps(["coal plant retirement", "Plant Scherer", "Sierra Club"])},

        {"hearing_id": 2, "segment_index": 2, "start_time": 100.0, "end_time": 160.0,
         "text": "PSC staff recommendation is to approve the proposed McIntosh gas plant as a necessary bridge resource while renewable capacity is built out.",
         "speaker": "Robert Trokey", "speaker_role": "PSC Staff", "topics": json.dumps(["PSC staff recommendation", "McIntosh gas plant"])},

        {"hearing_id": 2, "segment_index": 3, "start_time": 160.0, "end_time": 220.0,
         "text": "Georgia Watch has concerns about the cost allocation methodology. We believe industrial customers, particularly data centers, should bear a larger share of the capacity costs.",
         "speaker": "Georgia Watch Representative", "speaker_role": "Intervenor", "topics": json.dumps(["cost allocation", "data centers", "industrial customers"])},
    ]

    for seg in sample_segments:
        cursor.execute("""
            INSERT INTO segments (hearing_id, segment_index, start_time, end_time, text, speaker, speaker_role, topics)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            seg["hearing_id"],
            seg["segment_index"],
            seg["start_time"],
            seg["end_time"],
            seg["text"],
            seg["speaker"],
            seg["speaker_role"],
            seg["topics"]
        ))

    conn.commit()
    conn.close()
    print("Sample data added successfully")


if __name__ == "__main__":
    init_db()
    add_sample_data()
