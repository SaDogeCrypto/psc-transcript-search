"""
Hearings router for PSC Transcript Search API.
"""

from fastapi import APIRouter, HTTPException, Query
from database import get_cursor

router = APIRouter(prefix="/api/hearings", tags=["hearings"])


@router.get("")
def list_hearings(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100)
):
    """List all hearings in the database."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT h.*, COUNT(s.id) as segment_count
            FROM hearings h
            LEFT JOIN segments s ON h.id = s.hearing_id
            GROUP BY h.id
            ORDER BY h.hearing_date DESC NULLS LAST
            OFFSET %s LIMIT %s
        """, (skip, limit))

        hearings = cursor.fetchall()

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


@router.get("/{hearing_id}")
def get_hearing(hearing_id: int):
    """Get a specific hearing by ID."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT h.*, COUNT(s.id) as segment_count
            FROM hearings h
            LEFT JOIN segments s ON h.id = s.hearing_id
            WHERE h.id = %s
            GROUP BY h.id
        """, (hearing_id,))

        hearing = cursor.fetchone()

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


@router.get("/{hearing_id}/segments")
def get_hearing_segments(
    hearing_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500)
):
    """Get all segments for a specific hearing."""
    with get_cursor() as cursor:
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

    return {"segments": [dict(s) for s in segments]}


@router.get("/{hearing_id}/transcript")
def get_full_transcript(hearing_id: int):
    """Get the full transcript for a hearing as a single text."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT s.text, s.start_time, s.speaker, s.speaker_role
            FROM segments s
            WHERE s.hearing_id = %s
            ORDER BY s.start_time
        """, (hearing_id,))

        segments = cursor.fetchall()

    if not segments:
        raise HTTPException(status_code=404, detail="Hearing not found or has no segments")

    # Format as readable transcript
    lines = []
    for seg in segments:
        timestamp = format_timestamp(seg["start_time"])
        speaker = seg["speaker"] or seg["speaker_role"] or "Unknown"
        lines.append(f"[{timestamp}] {speaker}: {seg['text']}")

    return {
        "hearing_id": hearing_id,
        "transcript": "\n\n".join(lines),
        "segment_count": len(segments)
    }


def format_timestamp(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
