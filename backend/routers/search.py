"""
Search router for PSC Transcript Search API.
"""

from fastapi import APIRouter, Query
from models import SearchResponse, SearchResult
from database import get_cursor

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def fulltext_search(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(20, ge=1, le=100)
):
    """Full-text search across all transcript segments."""
    with get_cursor() as cursor:
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
            youtube_timestamp_url=f"https://www.youtube.com/watch?v={youtube_id}&t={start_seconds}s",
            rank=row["rank"]
        ))

    return SearchResponse(
        query=q,
        results=results,
        total_count=len(results),
        search_type="fulltext"
    )


@router.get("/semantic", response_model=SearchResponse)
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

    with get_cursor() as cursor:
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
            youtube_timestamp_url=f"https://www.youtube.com/watch?v={youtube_id}&t={start_seconds}s",
            similarity=row["similarity"]
        ))

    return SearchResponse(
        query=q,
        results=results,
        total_count=len(results),
        search_type="semantic"
    )


@router.get("/topics")
def search_by_topic(
    topic: str = Query(..., description="Topic to search for"),
    limit: int = Query(20, ge=1, le=100)
):
    """Search segments by extracted topic."""
    with get_cursor() as cursor:
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
                s.topics
            FROM segments s
            JOIN hearings h ON s.hearing_id = h.id
            WHERE %s = ANY(s.topics)
            ORDER BY s.start_time
            LIMIT %s
        """, (topic.lower(), limit))

        rows = cursor.fetchall()

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
            "topics": row["topics"],
            "youtube_url": f"https://www.youtube.com/watch?v={youtube_id}",
            "youtube_timestamp_url": f"https://www.youtube.com/watch?v={youtube_id}&t={start_seconds}s"
        })

    return {
        "topic": topic,
        "results": results,
        "total_count": len(results)
    }


@router.get("/speaker")
def search_by_speaker(
    speaker: str = Query(..., description="Speaker name or role to search for"),
    limit: int = Query(50, ge=1, le=200)
):
    """Search segments by speaker name or role."""
    with get_cursor() as cursor:
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
            WHERE s.speaker ILIKE %s OR s.speaker_role ILIKE %s
            ORDER BY h.hearing_date DESC, s.start_time
            LIMIT %s
        """, (f"%{speaker}%", f"%{speaker}%", limit))

        rows = cursor.fetchall()

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
        "speaker": speaker,
        "results": results,
        "total_count": len(results)
    }
