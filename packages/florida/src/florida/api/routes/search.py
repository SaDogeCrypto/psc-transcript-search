"""
Florida Unified Search API.

Full-text search across all Florida content:
- Dockets (title, utility name)
- Documents (extracted text)
- Transcripts (spoken content)
"""

import logging
from typing import Optional, List, Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel

from florida.models import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


class SearchResult(BaseModel):
    """Individual search result."""
    type: str  # 'docket', 'document', 'transcript'
    id: str
    title: str
    subtitle: Optional[str] = None
    excerpt: Optional[str] = None
    rank: float = 0.0
    url: Optional[str] = None


class SearchResponse(BaseModel):
    """Search response with results."""
    query: str
    total: int
    results: List[SearchResult]


@router.get("", response_model=SearchResponse)
def unified_search(
    q: str = Query(..., min_length=2, description="Search query"),
    content_type: Optional[Literal['docket', 'document', 'transcript']] = Query(
        None, description="Filter by content type"
    ),
    limit: int = Query(20, ge=1, le=100, description="Max results per type"),
    db: Session = Depends(get_db)
):
    """
    Search across all Florida content.

    Returns ranked results from dockets, documents, and transcripts.
    Use content_type to filter to a specific type.
    """
    results = []

    # Search dockets (title, utility name)
    if content_type in (None, 'docket'):
        try:
            docket_results = db.execute(text("""
                SELECT
                    'docket' as type,
                    docket_number as id,
                    COALESCE(title, 'Docket ' || docket_number) as title,
                    utility_name as subtitle,
                    NULL as excerpt,
                    ts_rank(
                        to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(utility_name, '')),
                        plainto_tsquery('english', :q)
                    ) as rank,
                    psc_docket_url as url
                FROM fl_dockets
                WHERE to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(utility_name, ''))
                      @@ plainto_tsquery('english', :q)
                ORDER BY rank DESC
                LIMIT :limit
            """), {"q": q, "limit": limit}).fetchall()

            for row in docket_results:
                results.append(SearchResult(
                    type=row.type,
                    id=row.id,
                    title=row.title,
                    subtitle=row.subtitle,
                    excerpt=row.excerpt,
                    rank=float(row.rank) if row.rank else 0.0,
                    url=row.url,
                ))
        except Exception as e:
            logger.warning(f"Docket search error: {e}")
            db.rollback()

    # Search documents (content text) - only if content_tsvector exists
    if content_type in (None, 'document'):
        try:
            # Check if content_tsvector column exists
            col_check = db.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'fl_documents' AND column_name = 'content_tsvector'
            """)).fetchone()

            if col_check:
                doc_results = db.execute(text("""
                    SELECT
                        'document' as type,
                        id::text as id,
                        title,
                        COALESCE(document_type, 'Document') as subtitle,
                        LEFT(content_text, 200) as excerpt,
                        ts_rank(content_tsvector, plainto_tsquery('english', :q)) as rank,
                        file_url as url
                    FROM fl_documents
                    WHERE content_tsvector @@ plainto_tsquery('english', :q)
                    ORDER BY rank DESC
                    LIMIT :limit
                """), {"q": q, "limit": limit}).fetchall()

                for row in doc_results:
                    results.append(SearchResult(
                        type=row.type,
                        id=row.id,
                        title=row.title,
                        subtitle=row.subtitle,
                        excerpt=row.excerpt,
                        rank=float(row.rank) if row.rank else 0.0,
                        url=row.url,
                    ))
        except Exception as e:
            logger.warning(f"Document search error: {e}")
            db.rollback()

    # Search transcript segments
    if content_type in (None, 'transcript'):
        try:
            segment_results = db.execute(text("""
                SELECT
                    'transcript' as type,
                    s.id::text as id,
                    LEFT(s.text, 150) as title,
                    COALESCE(s.speaker_name, s.speaker_label, 'Unknown Speaker')
                        || ' - ' || h.hearing_date::text as subtitle,
                    LEFT(s.text, 300) as excerpt,
                    ts_rank(s.text_tsvector, plainto_tsquery('english', :q)) as rank,
                    h.source_url as url
                FROM fl_transcript_segments s
                JOIN fl_hearings h ON s.hearing_id = h.id
                WHERE s.text_tsvector @@ plainto_tsquery('english', :q)
                ORDER BY rank DESC
                LIMIT :limit
            """), {"q": q, "limit": limit}).fetchall()

            for row in segment_results:
                title = row.title or ""
                excerpt = row.excerpt or ""
                results.append(SearchResult(
                    type=row.type,
                    id=row.id,
                    title=title[:150] + "..." if len(title) > 150 else title,
                    subtitle=row.subtitle,
                    excerpt=excerpt[:300] + "..." if len(excerpt) > 300 else excerpt,
                    rank=float(row.rank) if row.rank else 0.0,
                    url=row.url,
                ))
        except Exception as e:
            # Log the error for debugging
            logger.warning(f"Transcript search error: {e}")

    # Sort combined results by rank
    results.sort(key=lambda x: x.rank, reverse=True)

    # Limit total results
    results = results[:limit]

    return SearchResponse(
        query=q,
        total=len(results),
        results=results,
    )


@router.get("/dockets")
def search_dockets(
    q: str = Query(..., min_length=2),
    year: Optional[int] = None,
    sector: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Search dockets with optional filters."""
    # Build dynamic query with filters
    query_parts = ["""
        SELECT
            docket_number,
            title,
            utility_name,
            year,
            sector_code,
            status,
            filed_date,
            ts_rank(
                to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(utility_name, '')),
                plainto_tsquery('english', :q)
            ) as rank
        FROM fl_dockets
        WHERE to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(utility_name, ''))
              @@ plainto_tsquery('english', :q)
    """]

    params = {"q": q, "limit": limit}

    if year:
        query_parts.append("AND year = :year")
        params["year"] = year

    if sector:
        query_parts.append("AND sector_code = :sector")
        params["sector"] = sector

    query_parts.append("ORDER BY rank DESC LIMIT :limit")

    results = db.execute(text(" ".join(query_parts)), params).fetchall()

    return {
        "query": q,
        "filters": {"year": year, "sector": sector},
        "total": len(results),
        "results": [dict(row._mapping) for row in results],
    }


@router.get("/transcripts")
def search_transcripts(
    q: str = Query(..., min_length=2),
    speaker: Optional[str] = None,
    docket: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """Search transcript segments with optional filters."""
    query_parts = ["""
        SELECT
            s.id,
            s.text,
            s.speaker_name,
            s.speaker_role,
            s.start_time,
            h.id as hearing_id,
            h.hearing_date,
            h.docket_number,
            h.title as hearing_title,
            ts_rank(s.text_tsvector, plainto_tsquery('english', :q)) as rank
        FROM fl_transcript_segments s
        JOIN fl_hearings h ON s.hearing_id = h.id
        WHERE s.text_tsvector @@ plainto_tsquery('english', :q)
    """]

    params = {"q": q, "limit": limit}

    if speaker:
        query_parts.append("AND s.speaker_name ILIKE :speaker")
        params["speaker"] = f"%{speaker}%"

    if docket:
        query_parts.append("AND h.docket_number = :docket")
        params["docket"] = docket

    query_parts.append("ORDER BY rank DESC LIMIT :limit")

    results = db.execute(text(" ".join(query_parts)), params).fetchall()

    return {
        "query": q,
        "filters": {"speaker": speaker, "docket": docket},
        "total": len(results),
        "results": [dict(row._mapping) for row in results],
    }
