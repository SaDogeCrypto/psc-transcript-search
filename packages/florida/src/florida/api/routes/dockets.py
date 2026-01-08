"""
Florida Docket API routes.

Provides endpoints for docket listing, detail, and search.
"""

from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from florida.models import get_db, FLDocket

router = APIRouter(prefix="/dockets", tags=["dockets"])


class DocketResponse(BaseModel):
    """Docket response model."""
    id: int
    docket_number: str
    year: int
    sequence: int
    sector_code: Optional[str] = None
    title: Optional[str] = None
    utility_name: Optional[str] = None
    status: Optional[str] = None
    case_type: Optional[str] = None
    industry_type: Optional[str] = None
    filed_date: Optional[date] = None
    closed_date: Optional[date] = None
    psc_docket_url: Optional[str] = None

    class Config:
        from_attributes = True


class DocketListResponse(BaseModel):
    """Paginated docket list response."""
    items: List[DocketResponse]
    total: int
    page: int
    per_page: int
    pages: int


class DocketStats(BaseModel):
    """Docket statistics."""
    total: int
    open: int
    closed: int
    by_sector: dict
    by_year: dict


@router.get("", response_model=DocketListResponse)
def list_dockets(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    year: Optional[int] = None,
    status: Optional[str] = None,
    sector: Optional[str] = None,
    utility: Optional[str] = None,
    case_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List dockets with pagination and filtering.

    Query parameters:
    - page: Page number (1-indexed)
    - per_page: Results per page (max 200)
    - year: Filter by year
    - status: Filter by status (open/closed)
    - sector: Filter by sector code (EI, GU, etc.)
    - utility: Filter by utility name (partial match)
    - case_type: Filter by case type
    """
    query = db.query(FLDocket)

    if year:
        query = query.filter(FLDocket.year == year)
    if status:
        query = query.filter(FLDocket.status == status)
    if sector:
        query = query.filter(FLDocket.sector_code == sector)
    if utility:
        query = query.filter(FLDocket.utility_name.ilike(f"%{utility}%"))
    if case_type:
        query = query.filter(FLDocket.case_type.ilike(f"%{case_type}%"))

    total = query.count()
    pages = (total + per_page - 1) // per_page

    dockets = query.order_by(FLDocket.filed_date.desc()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    return DocketListResponse(
        items=[DocketResponse.model_validate(d) for d in dockets],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get("/stats", response_model=DocketStats)
def get_docket_stats(db: Session = Depends(get_db)):
    """Get docket statistics."""
    total = db.query(func.count(FLDocket.id)).scalar() or 0
    open_count = db.query(func.count(FLDocket.id)).filter(
        FLDocket.status == 'open'
    ).scalar() or 0
    closed_count = db.query(func.count(FLDocket.id)).filter(
        FLDocket.status == 'closed'
    ).scalar() or 0

    # By sector
    by_sector = {}
    sector_counts = db.query(
        FLDocket.sector_code,
        func.count(FLDocket.id)
    ).group_by(FLDocket.sector_code).all()
    for sector, count in sector_counts:
        if sector:
            by_sector[sector] = count

    # By year
    by_year = {}
    year_counts = db.query(
        FLDocket.year,
        func.count(FLDocket.id)
    ).group_by(FLDocket.year).order_by(FLDocket.year.desc()).limit(10).all()
    for year, count in year_counts:
        by_year[str(year)] = count

    return DocketStats(
        total=total,
        open=open_count,
        closed=closed_count,
        by_sector=by_sector,
        by_year=by_year,
    )


@router.get("/{docket_number}", response_model=DocketResponse)
def get_docket(docket_number: str, db: Session = Depends(get_db)):
    """Get a specific docket by number."""
    docket = db.query(FLDocket).filter(
        FLDocket.docket_number == docket_number
    ).first()

    if not docket:
        raise HTTPException(status_code=404, detail="Docket not found")

    return DocketResponse.model_validate(docket)


@router.get("/search/{query}")
def search_dockets(
    query: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Search dockets by title or utility name.

    Simple text search - for full-text search, use /api/fl/search
    """
    dockets = db.query(FLDocket).filter(
        (FLDocket.title.ilike(f"%{query}%")) |
        (FLDocket.utility_name.ilike(f"%{query}%")) |
        (FLDocket.docket_number.ilike(f"%{query}%"))
    ).limit(limit).all()

    return [DocketResponse.model_validate(d) for d in dockets]
