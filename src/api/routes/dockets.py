"""
Docket API routes.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from src.api.dependencies import get_db
from src.api.schemas.docket import DocketResponse, DocketListResponse, DocketDetail
from src.core.models.docket import Docket
from src.core.models.document import Document
from src.core.models.hearing import Hearing

router = APIRouter()


@router.get("", response_model=DocketListResponse)
def list_dockets(
    state_code: Optional[str] = Query(None, description="Filter by state (FL, TX, etc.)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    docket_type: Optional[str] = Query(None, description="Filter by docket type"),
    year: Optional[int] = Query(None, description="Filter by filed year"),
    search: Optional[str] = Query(None, description="Search in docket number or title"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List dockets with optional filters.

    Supports filtering by state, status, type, year, and text search.
    """
    query = db.query(Docket)

    # Apply filters
    if state_code:
        query = query.filter(Docket.state_code == state_code.upper())
    if status:
        query = query.filter(Docket.status == status)
    if docket_type:
        query = query.filter(Docket.docket_type.ilike(f"%{docket_type}%"))
    if year:
        query = query.filter(func.extract('year', Docket.filed_date) == year)
    if search:
        query = query.filter(
            (Docket.docket_number.ilike(f"%{search}%")) |
            (Docket.title.ilike(f"%{search}%"))
        )

    # Get total count
    total = query.count()

    # Get paginated results
    dockets = query.order_by(
        Docket.filed_date.desc().nullslast()
    ).offset(offset).limit(limit).all()

    return DocketListResponse(
        items=[DocketResponse.model_validate(d) for d in dockets],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{docket_id}", response_model=DocketDetail)
def get_docket(
    docket_id: UUID,
    db: Session = Depends(get_db),
):
    """
    Get docket by ID with full details.

    Includes document and hearing counts, plus state-specific fields.
    """
    docket = db.query(Docket).filter(Docket.id == docket_id).first()

    if not docket:
        raise HTTPException(status_code=404, detail="Docket not found")

    # Get counts
    doc_count = db.query(Document).filter(Document.docket_id == docket_id).count()
    hearing_count = db.query(Hearing).filter(Hearing.docket_id == docket_id).count()

    # Build response
    response_data = {
        "id": docket.id,
        "state_code": docket.state_code,
        "docket_number": docket.docket_number,
        "title": docket.title,
        "description": docket.description,
        "status": docket.status,
        "docket_type": docket.docket_type,
        "filed_date": docket.filed_date,
        "closed_date": docket.closed_date,
        "document_count": doc_count,
        "hearing_count": hearing_count,
    }

    # Add Florida-specific fields if available
    if hasattr(docket, 'fl_details') and docket.fl_details:
        fl = docket.fl_details
        response_data.update({
            "year": fl.year,
            "sector_code": fl.sector_code,
            "applicant_name": fl.applicant_name,
            "is_rate_case": fl.is_rate_case,
            "requested_revenue_increase": float(fl.requested_revenue_increase) if fl.requested_revenue_increase else None,
            "approved_revenue_increase": float(fl.approved_revenue_increase) if fl.approved_revenue_increase else None,
            "commissioner_assignments": fl.commissioner_assignments,
            "related_dockets": fl.related_dockets,
        })

    return DocketDetail(**response_data)


@router.get("/by-number/{docket_number}", response_model=DocketDetail)
def get_docket_by_number(
    docket_number: str,
    state_code: str = Query("FL", description="State code"),
    db: Session = Depends(get_db),
):
    """
    Get docket by docket number.

    Requires state_code since docket numbers are only unique within a state.
    """
    docket = db.query(Docket).filter(
        Docket.state_code == state_code.upper(),
        Docket.docket_number == docket_number,
    ).first()

    if not docket:
        raise HTTPException(status_code=404, detail="Docket not found")

    # Reuse get_docket logic
    return get_docket(docket.id, db)


@router.get("/{docket_id}/documents")
def get_docket_documents(
    docket_id: UUID,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Get documents for a docket."""
    from src.api.schemas.document import DocumentResponse, DocumentListResponse

    # Verify docket exists
    docket = db.query(Docket).filter(Docket.id == docket_id).first()
    if not docket:
        raise HTTPException(status_code=404, detail="Docket not found")

    query = db.query(Document).filter(Document.docket_id == docket_id)
    total = query.count()

    documents = query.order_by(
        Document.filed_date.desc().nullslast()
    ).offset(offset).limit(limit).all()

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{docket_id}/hearings")
def get_docket_hearings(
    docket_id: UUID,
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Get hearings for a docket."""
    from src.api.schemas.hearing import HearingResponse, HearingListResponse

    # Verify docket exists
    docket = db.query(Docket).filter(Docket.id == docket_id).first()
    if not docket:
        raise HTTPException(status_code=404, detail="Docket not found")

    query = db.query(Hearing).filter(Hearing.docket_id == docket_id)
    total = query.count()

    hearings = query.order_by(
        Hearing.hearing_date.desc().nullslast()
    ).offset(offset).limit(limit).all()

    # Build response with analysis summaries
    items = []
    for h in hearings:
        item_data = {
            "id": h.id,
            "state_code": h.state_code,
            "docket_id": h.docket_id,
            "docket_number": h.docket_number,
            "title": h.title,
            "hearing_type": h.hearing_type,
            "hearing_date": h.hearing_date,
            "duration_seconds": h.duration_seconds,
            "transcript_status": h.transcript_status,
            "video_url": h.video_url,
        }

        if h.analysis:
            item_data["one_sentence_summary"] = h.analysis.one_sentence_summary
            item_data["utility_name"] = h.analysis.utility_name
            item_data["sector"] = h.analysis.sector

        items.append(HearingResponse(**item_data))

    return HearingListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )
