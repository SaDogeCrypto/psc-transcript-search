"""
Document API routes.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.api.schemas.document import DocumentResponse, DocumentListResponse, DocumentDetail
from src.core.models.document import Document
from src.core.models.docket import Docket

router = APIRouter()


@router.get("", response_model=DocumentListResponse)
def list_documents(
    state_code: Optional[str] = Query(None, description="Filter by state"),
    docket_number: Optional[str] = Query(None, description="Filter by docket number"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    search: Optional[str] = Query(None, description="Search in title"),
    limit: int = Query(50, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    List documents with optional filters.
    """
    query = db.query(Document)

    # Apply filters
    if state_code:
        query = query.filter(Document.state_code == state_code.upper())
    if docket_number:
        # Join with docket to filter by docket number
        query = query.join(Docket).filter(Docket.docket_number == docket_number)
    if document_type:
        query = query.filter(Document.document_type.ilike(f"%{document_type}%"))
    if search:
        query = query.filter(Document.title.ilike(f"%{search}%"))

    # Get total count
    total = query.count()

    # Get paginated results
    documents = query.order_by(
        Document.filed_date.desc().nullslast()
    ).offset(offset).limit(limit).all()

    # Build response with docket numbers
    items = []
    for doc in documents:
        item_data = {
            "id": doc.id,
            "state_code": doc.state_code,
            "docket_id": doc.docket_id,
            "title": doc.title,
            "document_type": doc.document_type,
            "filed_date": doc.filed_date,
            "file_url": doc.file_url,
        }

        # Add docket number if available
        if doc.docket:
            item_data["docket_number"] = doc.docket.docket_number

        items.append(DocumentResponse(**item_data))

    return DocumentListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: UUID,
    include_content: bool = Query(False, description="Include full text content"),
    db: Session = Depends(get_db),
):
    """
    Get document by ID with full details.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    response_data = {
        "id": doc.id,
        "state_code": doc.state_code,
        "docket_id": doc.docket_id,
        "title": doc.title,
        "document_type": doc.document_type,
        "filed_date": doc.filed_date,
        "filing_party": doc.filing_party,
        "file_url": doc.file_url,
        "file_size_bytes": doc.file_size_bytes,
        "file_type": doc.file_type,
        "page_count": doc.page_count,
    }

    # Add docket number
    if doc.docket:
        response_data["docket_number"] = doc.docket.docket_number

    # Optionally include content
    if include_content:
        response_data["content_text"] = doc.content_text

    # Add Florida-specific fields
    if hasattr(doc, 'fl_details') and doc.fl_details:
        fl = doc.fl_details
        response_data.update({
            "thunderstone_id": fl.thunderstone_id,
            "profile": fl.profile,
        })

    return DocumentDetail(**response_data)


@router.get("/types")
def get_document_types(
    state_code: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Get distinct document types for filtering.
    """
    from sqlalchemy import func

    query = db.query(
        Document.document_type,
        func.count(Document.id).label('count')
    ).filter(
        Document.document_type.isnot(None)
    )

    if state_code:
        query = query.filter(Document.state_code == state_code.upper())

    results = query.group_by(Document.document_type).order_by(
        func.count(Document.id).desc()
    ).all()

    return [
        {"type": r.document_type, "count": r.count}
        for r in results
    ]
