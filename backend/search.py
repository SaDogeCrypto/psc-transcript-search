"""
Search logic for PSC Transcript Search.
"""

from database import get_cursor
from models import SearchResult


def fulltext_search(query: str, limit: int = 20) -> list[SearchResult]:
    """Perform full-text search using PostgreSQL's built-in search."""
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
        """, (query, query, limit))

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

    return results


def semantic_search(query: str, limit: int = 20) -> list[SearchResult]:
    """Perform semantic search using vector embeddings."""
    from openai import OpenAI

    client = OpenAI()

    # Generate embedding for query
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=query
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

    return results


def hybrid_search(query: str, limit: int = 20, fulltext_weight: float = 0.5) -> list[SearchResult]:
    """
    Combine full-text and semantic search results.
    Uses reciprocal rank fusion (RRF) to merge rankings.
    """
    fulltext_results = fulltext_search(query, limit=limit * 2)
    semantic_results = semantic_search(query, limit=limit * 2)

    # Create score maps using RRF
    k = 60  # RRF constant
    scores = {}

    for rank, result in enumerate(fulltext_results):
        key = result.segment_id
        rrf_score = fulltext_weight / (k + rank + 1)
        scores[key] = scores.get(key, 0) + rrf_score
        if key not in scores:
            scores[key] = {"result": result, "score": 0}
        scores[key] = {"result": result, "score": scores.get(key, {}).get("score", 0) + rrf_score}

    semantic_weight = 1 - fulltext_weight
    for rank, result in enumerate(semantic_results):
        key = result.segment_id
        rrf_score = semantic_weight / (k + rank + 1)
        if key in scores:
            scores[key]["score"] += rrf_score
        else:
            scores[key] = {"result": result, "score": rrf_score}

    # Sort by combined score and return top results
    sorted_results = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    return [item["result"] for item in sorted_results[:limit]]
