"""
FastAPI backend for PSC Transcript Search (SQLite version for testing).
"""

import os
import json
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from database_sqlite import get_connection, init_db, add_sample_data

# Initialize database on startup
init_db()
# Only add sample data if not in production (check if real data exists)
if os.getenv("SKIP_SAMPLE_DATA") != "true":
    add_sample_data()

app = FastAPI(title="PSC Transcript Search", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Models
class SearchResult(BaseModel):
    segment_id: int
    hearing_id: int
    youtube_id: str
    hearing_title: str
    start_time: float
    end_time: float
    text: str
    speaker: str | None
    speaker_role: str | None
    youtube_url: str
    youtube_timestamp_url: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total_count: int


# Endpoints
@app.get("/")
def root():
    return {"status": "ok", "message": "PSC Transcript Search API (SQLite)"}


@app.get("/api/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=100)
):
    """Full-text search across all transcript segments."""
    conn = get_connection()
    cursor = conn.cursor()

    # Use SQLite FTS5 for full-text search
    cursor.execute("""
        SELECT
            s.id as segment_id,
            s.hearing_id,
            h.youtube_id,
            h.title as hearing_title,
            s.start_time,
            s.end_time,
            s.text,
            s.speaker,
            s.speaker_role
        FROM segments s
        JOIN hearings h ON s.hearing_id = h.id
        JOIN segments_fts fts ON s.id = fts.rowid
        WHERE segments_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (q, limit))

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        youtube_id = row["youtube_id"]
        start_seconds = int(row["start_time"])

        results.append(SearchResult(
            segment_id=row["segment_id"],
            hearing_id=row["hearing_id"],
            youtube_id=youtube_id,
            hearing_title=row["hearing_title"],
            start_time=row["start_time"],
            end_time=row["end_time"],
            text=row["text"],
            speaker=row["speaker"],
            speaker_role=row["speaker_role"],
            youtube_url=f"https://www.youtube.com/watch?v={youtube_id}",
            youtube_timestamp_url=f"https://www.youtube.com/watch?v={youtube_id}&t={start_seconds}s"
        ))

    return SearchResponse(
        query=q,
        results=results,
        total_count=len(results)
    )


@app.get("/api/search/simple")
def simple_search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=100)
):
    """Simple LIKE-based search (fallback if FTS fails)."""
    conn = get_connection()
    cursor = conn.cursor()

    # Simple LIKE search
    cursor.execute("""
        SELECT
            s.id as segment_id,
            s.hearing_id,
            h.youtube_id,
            h.title as hearing_title,
            s.start_time,
            s.end_time,
            s.text,
            s.speaker,
            s.speaker_role
        FROM segments s
        JOIN hearings h ON s.hearing_id = h.id
        WHERE s.text LIKE ?
        ORDER BY s.start_time
        LIMIT ?
    """, (f"%{q}%", limit))

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        youtube_id = row["youtube_id"]
        start_seconds = int(row["start_time"])

        results.append({
            "segment_id": row["segment_id"],
            "hearing_id": row["hearing_id"],
            "youtube_id": youtube_id,
            "hearing_title": row["hearing_title"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "text": row["text"],
            "speaker": row["speaker"],
            "speaker_role": row["speaker_role"],
            "youtube_url": f"https://www.youtube.com/watch?v={youtube_id}",
            "youtube_timestamp_url": f"https://www.youtube.com/watch?v={youtube_id}&t={start_seconds}s"
        })

    return {
        "query": q,
        "results": results,
        "total_count": len(results)
    }


@app.get("/api/hearings")
def list_hearings():
    """List all hearings in the database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT h.*, COUNT(s.id) as segment_count
        FROM hearings h
        LEFT JOIN segments s ON h.id = s.hearing_id
        GROUP BY h.id
        ORDER BY h.created_at DESC
    """)

    hearings = cursor.fetchall()
    conn.close()

    return {"hearings": hearings}


@app.get("/api/hearings/{hearing_id}")
def get_hearing(hearing_id: int):
    """Get a specific hearing by ID."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT h.*, COUNT(s.id) as segment_count
        FROM hearings h
        LEFT JOIN segments s ON h.id = s.hearing_id
        WHERE h.id = ?
        GROUP BY h.id
    """, (hearing_id,))

    hearing = cursor.fetchone()
    conn.close()

    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    return {"hearing": hearing}


@app.get("/api/hearings/{hearing_id}/segments")
def get_hearing_segments(hearing_id: int, skip: int = 0, limit: int = 100):
    """Get all segments for a specific hearing."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.id, s.segment_index, s.start_time, s.end_time, s.text,
               s.speaker, s.speaker_role, s.topics,
               h.youtube_id, h.title as hearing_title
        FROM segments s
        JOIN hearings h ON s.hearing_id = h.id
        WHERE s.hearing_id = ?
        ORDER BY s.start_time
        LIMIT ? OFFSET ?
    """, (hearing_id, limit, skip))

    segments = cursor.fetchall()
    conn.close()

    return {"segments": segments}


@app.get("/api/stats")
def get_stats():
    """Get database statistics."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as count FROM hearings")
    hearing_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM segments")
    segment_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COALESCE(SUM(duration_seconds), 0) as total FROM hearings")
    total_duration = cursor.fetchone()["total"]

    conn.close()

    return {
        "hearings": hearing_count,
        "segments": segment_count,
        "total_hours": round(total_duration / 3600, 1) if total_duration else 0
    }


@app.get("/api/search/speaker")
def search_by_speaker(
    speaker: str = Query(..., description="Speaker name or role"),
    limit: int = Query(50, ge=1, le=200)
):
    """Search segments by speaker."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            s.id as segment_id,
            s.hearing_id,
            h.youtube_id,
            h.title as hearing_title,
            s.start_time,
            s.end_time,
            s.text,
            s.speaker,
            s.speaker_role
        FROM segments s
        JOIN hearings h ON s.hearing_id = h.id
        WHERE s.speaker LIKE ? OR s.speaker_role LIKE ?
        ORDER BY s.start_time
        LIMIT ?
    """, (f"%{speaker}%", f"%{speaker}%", limit))

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        youtube_id = row["youtube_id"]
        start_seconds = int(row["start_time"])
        results.append({
            "segment_id": row["segment_id"],
            "hearing_id": row["hearing_id"],
            "youtube_id": youtube_id,
            "hearing_title": row["hearing_title"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "text": row["text"],
            "speaker": row["speaker"],
            "speaker_role": row["speaker_role"],
            "youtube_url": f"https://www.youtube.com/watch?v={youtube_id}",
            "youtube_timestamp_url": f"https://www.youtube.com/watch?v={youtube_id}&t={start_seconds}s"
        })

    return {"speaker": speaker, "results": results, "total_count": len(results)}


# =============================================================================
# INSIGHTS ENDPOINTS
# =============================================================================

from pathlib import Path

INSIGHTS_DIR = Path(__file__).parent.parent / "data" / "insights"


@app.get("/api/insights")
def list_insights():
    """List all available hearing insights."""
    if not INSIGHTS_DIR.exists():
        return {"insights": [], "count": 0}

    insights = []
    for file in INSIGHTS_DIR.glob("*_insights.json"):
        try:
            with open(file) as f:
                data = json.load(f)
            hearing_insights = data.get("hearing_insights", {})
            insights.append({
                "hearing_id": data.get("hearing_id"),
                "file": file.name,
                "processed_at": data.get("processed_at"),
                "one_sentence_summary": hearing_insights.get("one_sentence_summary", ""),
                "commissioner_mood": hearing_insights.get("commissioner_mood", ""),
                "confidence_score": hearing_insights.get("confidence_score", 0),
                "notable_segments": sum(1 for s in data.get("segment_insights", []) if s.get("is_notable"))
            })
        except Exception as e:
            continue

    return {"insights": insights, "count": len(insights)}


@app.get("/api/insights/{hearing_id}")
def get_insights(hearing_id: str):
    """Get full insights for a specific hearing."""
    # Try different file naming patterns
    possible_files = [
        INSIGHTS_DIR / f"{hearing_id}_insights.json",
        INSIGHTS_DIR / f"{hearing_id}.json",
    ]

    for file_path in possible_files:
        if file_path.exists():
            with open(file_path) as f:
                data = json.load(f)
            return data

    raise HTTPException(status_code=404, detail=f"Insights not found for hearing {hearing_id}")


@app.get("/api/insights/{hearing_id}/summary")
def get_insights_summary(hearing_id: str):
    """Get executive summary and key takeaways for a hearing."""
    data = get_insights(hearing_id)
    hi = data.get("hearing_insights", {})

    return {
        "hearing_id": hearing_id,
        "one_sentence_summary": hi.get("one_sentence_summary", ""),
        "executive_summary": hi.get("executive_summary", ""),
        "key_takeaways": hi.get("key_takeaways", []),
        "central_dispute": hi.get("central_dispute", ""),
        "utility_position": hi.get("utility_position", ""),
        "opposition_position": hi.get("opposition_position", ""),
        "commissioner_mood": hi.get("commissioner_mood", ""),
        "confidence_score": hi.get("confidence_score", 0)
    }


@app.get("/api/insights/{hearing_id}/notable")
def get_notable_segments(hearing_id: str):
    """Get notable segments flagged for review."""
    data = get_insights(hearing_id)

    notable = [
        s for s in data.get("segment_insights", [])
        if s.get("is_notable")
    ]

    return {
        "hearing_id": hearing_id,
        "notable_segments": notable,
        "count": len(notable)
    }


@app.get("/api/insights/{hearing_id}/outcomes")
def get_potential_outcomes(hearing_id: str):
    """Get potential outcomes analysis."""
    data = get_insights(hearing_id)
    hi = data.get("hearing_insights", {})

    return {
        "hearing_id": hearing_id,
        "potential_outcomes": hi.get("potential_outcomes", []),
        "utility_vulnerabilities": hi.get("utility_vulnerabilities", []),
        "utility_commitments": hi.get("utility_commitments", []),
        "disputed_facts": hi.get("disputed_facts", [])
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
