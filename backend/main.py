"""
FastAPI backend for PSC Transcript Search.
"""

import os
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="PSC Transcript Search", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/psc_transcripts")


def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


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


class HearingResponse(BaseModel):
    id: int
    youtube_id: str
    title: str
    description: str | None
    hearing_date: str | None
    duration_seconds: int | None
    youtube_url: str
    transcript_status: str
    segment_count: int


# Endpoints
@app.get("/")
def root():
    return {"status": "ok", "message": "PSC Transcript Search API"}


@app.get("/api/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=100)
):
    """Full-text search across all transcript segments."""
    conn = get_db()
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
            s.speaker_role,
            ts_rank(to_tsvector('english', s.text), plainto_tsquery('english', %s)) as rank
        FROM segments s
        JOIN hearings h ON s.hearing_id = h.id
        WHERE to_tsvector('english', s.text) @@ plainto_tsquery('english', %s)
        ORDER BY rank DESC
        LIMIT %s
    """, (q, q, limit))

    rows = cursor.fetchall()

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

    cursor.close()
    conn.close()

    return SearchResponse(
        query=q,
        results=results,
        total_count=len(results)
    )


@app.get("/api/search/semantic", response_model=SearchResponse)
def semantic_search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=100)
):
    """Semantic search using embeddings."""
    from openai import OpenAI

    client = OpenAI()

    # Generate embedding for query
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=q
    )
    query_embedding = response.data[0].embedding

    conn = get_db()
    cursor = conn.cursor()

    # Search by vector similarity
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
            s.speaker_role,
            1 - (s.embedding <=> %s::vector) as similarity
        FROM segments s
        JOIN hearings h ON s.hearing_id = h.id
        WHERE s.embedding IS NOT NULL
        ORDER BY s.embedding <=> %s::vector
        LIMIT %s
    """, (query_embedding, query_embedding, limit))

    rows = cursor.fetchall()

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

    cursor.close()
    conn.close()

    return SearchResponse(
        query=q,
        results=results,
        total_count=len(results)
    )


@app.get("/api/hearings")
def list_hearings():
    """List all hearings in the database."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT h.*, COUNT(s.id) as segment_count
        FROM hearings h
        LEFT JOIN segments s ON h.id = s.hearing_id
        GROUP BY h.id
        ORDER BY h.hearing_date DESC NULLS LAST
    """)

    hearings = cursor.fetchall()
    cursor.close()
    conn.close()

    # Convert dates to strings for JSON serialization
    result = []
    for h in hearings:
        hearing_dict = dict(h)
        if hearing_dict.get("hearing_date"):
            hearing_dict["hearing_date"] = str(hearing_dict["hearing_date"])
        if hearing_dict.get("created_at"):
            hearing_dict["created_at"] = str(hearing_dict["created_at"])
        if hearing_dict.get("updated_at"):
            hearing_dict["updated_at"] = str(hearing_dict["updated_at"])
        result.append(hearing_dict)

    return {"hearings": result}


@app.get("/api/hearings/{hearing_id}")
def get_hearing(hearing_id: int):
    """Get a specific hearing by ID."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT h.*, COUNT(s.id) as segment_count
        FROM hearings h
        LEFT JOIN segments s ON h.id = s.hearing_id
        WHERE h.id = %s
        GROUP BY h.id
    """, (hearing_id,))

    hearing = cursor.fetchone()
    cursor.close()
    conn.close()

    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")

    hearing_dict = dict(hearing)
    if hearing_dict.get("hearing_date"):
        hearing_dict["hearing_date"] = str(hearing_dict["hearing_date"])
    if hearing_dict.get("created_at"):
        hearing_dict["created_at"] = str(hearing_dict["created_at"])
    if hearing_dict.get("updated_at"):
        hearing_dict["updated_at"] = str(hearing_dict["updated_at"])

    return {"hearing": hearing_dict}


@app.get("/api/hearings/{hearing_id}/segments")
def get_hearing_segments(hearing_id: int, skip: int = 0, limit: int = 100):
    """Get all segments for a specific hearing."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT s.id, s.segment_index, s.start_time, s.end_time, s.text,
               s.speaker, s.speaker_role, s.topics,
               h.youtube_id, h.title as hearing_title
        FROM segments s
        JOIN hearings h ON s.hearing_id = h.id
        WHERE s.hearing_id = %s
        ORDER BY s.start_time
        OFFSET %s LIMIT %s
    """, (hearing_id, skip, limit))

    segments = cursor.fetchall()
    cursor.close()
    conn.close()

    return {"segments": [dict(s) for s in segments]}


@app.get("/api/stats")
def get_stats():
    """Get database statistics."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as count FROM hearings")
    hearing_count = cursor.fetchone()["count"]

    cursor.execute("SELECT COUNT(*) as count FROM segments")
    segment_count = cursor.fetchone()["count"]

    cursor.execute("SELECT SUM(duration_seconds) as total FROM hearings")
    total_duration = cursor.fetchone()["total"] or 0

    cursor.close()
    conn.close()

    return {
        "hearings": hearing_count,
        "segments": segment_count,
        "total_hours": round(total_duration / 3600, 1)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
