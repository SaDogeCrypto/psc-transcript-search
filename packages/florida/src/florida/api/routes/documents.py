"""
Florida Document API routes.

Provides endpoints for document listing and search.
"""

from datetime import date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from florida.models import get_db, FLDocument

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentResponse(BaseModel):
    """Document response model."""
    id: int
    thunderstone_id: Optional[str] = None
    title: str
    document_type: Optional[str] = None
    profile: Optional[str] = None
    docket_number: Optional[str] = None
    file_url: Optional[str] = None
    file_type: Optional[str] = None
    file_size_bytes: Optional[int] = None
    filed_date: Optional[date] = None
    filer_name: Optional[str] = None
    document_number: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentListResponse(BaseModel):
    """Paginated document list response."""
    items: List[DocumentResponse]
    total: int
    page: int
    per_page: int
    pages: int


class DocumentStats(BaseModel):
    """Document statistics."""
    total: int
    by_type: dict
    by_profile: dict


@router.get("", response_model=DocumentListResponse)
def list_documents(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    docket: Optional[str] = None,
    document_type: Optional[str] = None,
    profile: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    List documents with pagination and filtering.

    Query parameters:
    - page: Page number (1-indexed)
    - per_page: Results per page (max 200)
    - docket: Filter by docket number
    - document_type: Filter by document type
    - profile: Filter by Thunderstone profile
    """
    query = db.query(FLDocument)

    if docket:
        query = query.filter(FLDocument.docket_number == docket)
    if document_type:
        query = query.filter(FLDocument.document_type.ilike(f"%{document_type}%"))
    if profile:
        query = query.filter(FLDocument.profile == profile)

    total = query.count()
    pages = (total + per_page - 1) // per_page

    documents = query.order_by(FLDocument.filed_date.desc().nulls_last()).offset(
        (page - 1) * per_page
    ).limit(per_page).all()

    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in documents],
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


@router.get("/stats", response_model=DocumentStats)
def get_document_stats(db: Session = Depends(get_db)):
    """Get document statistics."""
    total = db.query(func.count(FLDocument.id)).scalar() or 0

    # By type
    by_type = {}
    type_counts = db.query(
        FLDocument.document_type,
        func.count(FLDocument.id)
    ).group_by(FLDocument.document_type).order_by(func.count(FLDocument.id).desc()).limit(20).all()
    for doc_type, count in type_counts:
        if doc_type:
            by_type[doc_type] = count

    # By profile
    by_profile = {}
    profile_counts = db.query(
        FLDocument.profile,
        func.count(FLDocument.id)
    ).group_by(FLDocument.profile).all()
    for profile, count in profile_counts:
        if profile:
            by_profile[profile] = count

    return DocumentStats(
        total=total,
        by_type=by_type,
        by_profile=by_profile,
    )


@router.get("/by-docket/{docket_number}", response_model=List[DocumentResponse])
def get_documents_by_docket(
    docket_number: str,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """Get all documents for a specific docket."""
    documents = db.query(FLDocument).filter(
        FLDocument.docket_number == docket_number
    ).order_by(FLDocument.filed_date.desc().nulls_last()).limit(limit).all()

    return [DocumentResponse.model_validate(d) for d in documents]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: int, db: Session = Depends(get_db)):
    """Get a specific document by ID."""
    document = db.query(FLDocument).filter(
        FLDocument.id == document_id
    ).first()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentResponse.model_validate(document)


@router.get("/search/{query}")
def search_documents(
    query: str,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Search documents by title.

    Simple text search - for full-text search, use /api/fl/search
    """
    documents = db.query(FLDocument).filter(
        FLDocument.title.ilike(f"%{query}%")
    ).limit(limit).all()

    return [DocumentResponse.model_validate(d) for d in documents]
