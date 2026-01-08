"""
Search service - full-text and semantic search.

Provides:
- Full-text search across transcripts
- Semantic search using embeddings (if pgvector available)
- Faceted search with filters
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from sqlalchemy import func, or_, and_
from sqlalchemy.orm import Session

from src.core.models.hearing import Hearing
from src.core.models.transcript import TranscriptSegment
from src.core.models.analysis import Analysis

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Individual search result."""
    hearing_id: str
    title: str
    hearing_date: str
    state_code: str
    docket_number: Optional[str]
    snippet: str  # Matching text excerpt
    score: float  # Relevance score


@dataclass
class SearchResponse:
    """Search response with results and metadata."""
    results: List[SearchResult]
    total: int
    query: str
    filters: Dict[str, Any]


class SearchService:
    """
    Full-text and semantic search across hearing transcripts.

    Usage:
        search = SearchService(db)
        results = search.search_transcripts("rate case", state_code="FL")
    """

    def __init__(self, db: Session):
        self.db = db

    def search_transcripts(
        self,
        query: str,
        state_code: Optional[str] = None,
        docket_number: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        hearing_type: Optional[str] = None,
        utility: Optional[str] = None,
        sector: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SearchResponse:
        """
        Search transcripts with full-text matching.

        Args:
            query: Search query string
            state_code: Filter by state (FL, TX, etc.)
            docket_number: Filter by docket number
            date_from: Filter by date range start
            date_to: Filter by date range end
            hearing_type: Filter by hearing type
            utility: Filter by utility name
            sector: Filter by sector
            limit: Max results to return
            offset: Pagination offset

        Returns:
            SearchResponse with matching results
        """
        # Build base query
        base_query = self.db.query(
            Hearing.id,
            Hearing.title,
            Hearing.hearing_date,
            Hearing.state_code,
            Hearing.docket_number,
            Hearing.full_text,
        ).filter(
            Hearing.full_text.isnot(None)
        )

        # Apply filters
        if state_code:
            base_query = base_query.filter(Hearing.state_code == state_code.upper())

        if docket_number:
            base_query = base_query.filter(Hearing.docket_number.ilike(f"%{docket_number}%"))

        if date_from:
            base_query = base_query.filter(Hearing.hearing_date >= date_from)

        if date_to:
            base_query = base_query.filter(Hearing.hearing_date <= date_to)

        if hearing_type:
            base_query = base_query.filter(Hearing.hearing_type.ilike(f"%{hearing_type}%"))

        # Join with analysis for utility/sector filters
        if utility or sector:
            base_query = base_query.join(Analysis, Analysis.hearing_id == Hearing.id)
            if utility:
                base_query = base_query.filter(Analysis.utility_name.ilike(f"%{utility}%"))
            if sector:
                base_query = base_query.filter(Analysis.sector == sector)

        # Full-text search using ILIKE (basic implementation)
        # For production, use PostgreSQL full-text search or Elasticsearch
        if query:
            search_terms = query.split()
            conditions = []
            for term in search_terms:
                conditions.append(Hearing.full_text.ilike(f"%{term}%"))
            base_query = base_query.filter(and_(*conditions))

        # Get total count
        total = base_query.count()

        # Get paginated results
        hearings = base_query.order_by(
            Hearing.hearing_date.desc()
        ).offset(offset).limit(limit).all()

        # Build results with snippets
        results = []
        for h in hearings:
            snippet = self._extract_snippet(h.full_text, query)
            results.append(SearchResult(
                hearing_id=str(h.id),
                title=h.title or "Untitled Hearing",
                hearing_date=h.hearing_date.isoformat() if h.hearing_date else "",
                state_code=h.state_code,
                docket_number=h.docket_number,
                snippet=snippet,
                score=1.0,  # Basic implementation - no relevance scoring
            ))

        return SearchResponse(
            results=results,
            total=total,
            query=query,
            filters={
                "state_code": state_code,
                "docket_number": docket_number,
                "date_from": date_from,
                "date_to": date_to,
                "hearing_type": hearing_type,
                "utility": utility,
                "sector": sector,
            }
        )

    def search_segments(
        self,
        query: str,
        hearing_id: Optional[str] = None,
        speaker: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Search within transcript segments.

        Useful for finding specific quotes or speaker statements.

        Args:
            query: Search query
            hearing_id: Filter to specific hearing
            speaker: Filter by speaker name
            limit: Max results

        Returns:
            List of matching segments with context
        """
        base_query = self.db.query(TranscriptSegment).filter(
            TranscriptSegment.text.isnot(None)
        )

        if hearing_id:
            base_query = base_query.filter(TranscriptSegment.hearing_id == hearing_id)

        if speaker:
            base_query = base_query.filter(
                or_(
                    TranscriptSegment.speaker_name.ilike(f"%{speaker}%"),
                    TranscriptSegment.speaker_label.ilike(f"%{speaker}%")
                )
            )

        if query:
            base_query = base_query.filter(TranscriptSegment.text.ilike(f"%{query}%"))

        segments = base_query.order_by(
            TranscriptSegment.hearing_id,
            TranscriptSegment.segment_index
        ).limit(limit).all()

        return [
            {
                "id": str(seg.id),
                "hearing_id": str(seg.hearing_id),
                "segment_index": seg.segment_index,
                "start_time": seg.start_time,
                "end_time": seg.end_time,
                "text": seg.text,
                "speaker_name": seg.speaker_name,
                "speaker_label": seg.speaker_label,
                "timestamp": seg.timestamp_display,
            }
            for seg in segments
        ]

    def get_facets(
        self,
        state_code: Optional[str] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get facet counts for filtering.

        Returns counts of:
        - States
        - Hearing types
        - Sectors
        - Utilities
        """
        facets = {}

        # State counts
        state_query = self.db.query(
            Hearing.state_code,
            func.count(Hearing.id).label('count')
        ).filter(
            Hearing.full_text.isnot(None)
        ).group_by(Hearing.state_code)

        facets['states'] = [
            {"value": row.state_code, "count": row.count}
            for row in state_query.all()
        ]

        # Hearing type counts
        type_query = self.db.query(
            Hearing.hearing_type,
            func.count(Hearing.id).label('count')
        ).filter(
            Hearing.full_text.isnot(None),
            Hearing.hearing_type.isnot(None)
        )

        if state_code:
            type_query = type_query.filter(Hearing.state_code == state_code)

        type_query = type_query.group_by(Hearing.hearing_type)
        facets['hearing_types'] = [
            {"value": row.hearing_type, "count": row.count}
            for row in type_query.all()
        ]

        # Sector counts (from analysis)
        sector_query = self.db.query(
            Analysis.sector,
            func.count(Analysis.id).label('count')
        ).filter(
            Analysis.sector.isnot(None)
        ).group_by(Analysis.sector)

        facets['sectors'] = [
            {"value": row.sector, "count": row.count}
            for row in sector_query.all()
        ]

        # Top utilities
        utility_query = self.db.query(
            Analysis.utility_name,
            func.count(Analysis.id).label('count')
        ).filter(
            Analysis.utility_name.isnot(None)
        ).group_by(Analysis.utility_name).order_by(
            func.count(Analysis.id).desc()
        ).limit(20)

        facets['utilities'] = [
            {"value": row.utility_name, "count": row.count}
            for row in utility_query.all()
        ]

        return facets

    def _extract_snippet(self, text: str, query: str, context_chars: int = 200) -> str:
        """Extract a snippet around the first match."""
        if not text or not query:
            return text[:context_chars] + "..." if text else ""

        text_lower = text.lower()
        query_lower = query.lower()

        # Find first term match
        first_term = query.split()[0].lower() if query.split() else ""
        pos = text_lower.find(first_term)

        if pos == -1:
            return text[:context_chars] + "..."

        # Extract context around match
        start = max(0, pos - context_chars // 2)
        end = min(len(text), pos + len(first_term) + context_chars // 2)

        snippet = text[start:end]

        # Add ellipsis if truncated
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        return snippet
