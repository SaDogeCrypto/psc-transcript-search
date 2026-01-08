"""
Search API routes.
"""

from typing import Optional
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.schemas.search import SearchResponse, SearchResult, SearchFacets
from src.core.services.search import SearchService

router = APIRouter()


@router.get("", response_model=SearchResponse)
def search_transcripts(
    q: str = Query(..., min_length=1, description="Search query"),
    state_code: Optional[str] = Query(None, description="Filter by state"),
    docket_number: Optional[str] = Query(None, description="Filter by docket"),
    date_from: Optional[date] = Query(None, description="Filter from date"),
    date_to: Optional[date] = Query(None, description="Filter to date"),
    hearing_type: Optional[str] = Query(None, description="Filter by hearing type"),
    utility: Optional[str] = Query(None, description="Filter by utility"),
    sector: Optional[str] = Query(None, description="Filter by sector"),
    limit: int = Query(20, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Search hearing transcripts.

    Full-text search across transcript content with optional filters.
    Returns matching hearings with text snippets.
    """
    search_service = SearchService(db)

    result = search_service.search_transcripts(
        query=q,
        state_code=state_code,
        docket_number=docket_number,
        date_from=str(date_from) if date_from else None,
        date_to=str(date_to) if date_to else None,
        hearing_type=hearing_type,
        utility=utility,
        sector=sector,
        limit=limit,
        offset=offset,
    )

    return SearchResponse(
        results=[
            SearchResult(
                hearing_id=r.hearing_id,
                title=r.title,
                hearing_date=r.hearing_date,
                state_code=r.state_code,
                docket_number=r.docket_number,
                snippet=r.snippet,
                score=r.score,
            )
            for r in result.results
        ],
        total=result.total,
        query=result.query,
        filters=result.filters,
    )


@router.get("/facets", response_model=SearchFacets)
def get_search_facets(
    state_code: Optional[str] = Query(None, description="Filter facets by state"),
    db: Session = Depends(get_db),
):
    """
    Get facet counts for search filtering.

    Returns counts of:
    - States
    - Hearing types
    - Sectors
    - Top utilities
    """
    search_service = SearchService(db)
    facets = search_service.get_facets(state_code=state_code)

    return SearchFacets(
        states=facets.get("states", []),
        hearing_types=facets.get("hearing_types", []),
        sectors=facets.get("sectors", []),
        utilities=facets.get("utilities", []),
    )


@router.get("/segments")
def search_segments(
    q: str = Query(..., min_length=1, description="Search query"),
    hearing_id: Optional[str] = Query(None, description="Filter to specific hearing"),
    speaker: Optional[str] = Query(None, description="Filter by speaker"),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
):
    """
    Search within transcript segments.

    Useful for finding specific quotes or statements by speaker.
    """
    search_service = SearchService(db)

    segments = search_service.search_segments(
        query=q,
        hearing_id=hearing_id,
        speaker=speaker,
        limit=limit,
    )

    return {
        "results": segments,
        "total": len(segments),
        "query": q,
    }


@router.get("/suggest")
def search_suggestions(
    q: str = Query(..., min_length=2, description="Partial query for suggestions"),
    state_code: Optional[str] = Query(None),
    limit: int = Query(10, le=20),
    db: Session = Depends(get_db),
):
    """
    Get search suggestions based on partial query.

    Returns suggestions for:
    - Docket numbers
    - Utility names
    - Common terms
    """
    from sqlalchemy import func
    from src.core.models.docket import Docket
    from src.core.models.analysis import Analysis

    suggestions = []

    # Docket number suggestions
    docket_query = db.query(Docket.docket_number).filter(
        Docket.docket_number.ilike(f"%{q}%")
    )
    if state_code:
        docket_query = docket_query.filter(Docket.state_code == state_code.upper())

    dockets = docket_query.limit(5).all()
    for d in dockets:
        suggestions.append({
            "type": "docket",
            "value": d.docket_number,
            "label": f"Docket: {d.docket_number}",
        })

    # Utility name suggestions
    utility_query = db.query(Analysis.utility_name).filter(
        Analysis.utility_name.ilike(f"%{q}%"),
        Analysis.utility_name.isnot(None),
    ).distinct().limit(5)

    utilities = utility_query.all()
    for u in utilities:
        suggestions.append({
            "type": "utility",
            "value": u.utility_name,
            "label": f"Utility: {u.utility_name}",
        })

    return {
        "suggestions": suggestions[:limit],
        "query": q,
    }
