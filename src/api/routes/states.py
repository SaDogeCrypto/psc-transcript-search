"""
State API routes.
"""

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.dependencies import get_db
from src.core.models.hearing import Hearing
from src.states.registry import StateRegistry

router = APIRouter()


class StateResponse(BaseModel):
    """State information."""
    code: str
    name: str
    commission_name: str | None = None
    hearing_count: int = 0
    docket_format: str | None = None


@router.get("", response_model=List[StateResponse])
def list_states(db: Session = Depends(get_db)):
    """
    List all available states with hearing counts.
    """
    # Get all registered states from registry
    state_codes = StateRegistry.get_available_states()

    # Get hearing counts per state
    hearing_counts = dict(
        db.query(
            Hearing.state_code,
            func.count(Hearing.id)
        ).group_by(Hearing.state_code).all()
    )

    states = []
    for code in sorted(state_codes):
        metadata = StateRegistry.get_metadata(code) or {}
        states.append(StateResponse(
            code=code,
            name=metadata.get("full_name", code),
            commission_name=metadata.get("commission_name"),
            hearing_count=hearing_counts.get(code, 0),
            docket_format=metadata.get("docket_format"),
        ))

    return states


@router.get("/{state_code}", response_model=StateResponse)
def get_state(state_code: str, db: Session = Depends(get_db)):
    """
    Get state information by code.
    """
    state_code = state_code.upper()

    # Get metadata from registry
    metadata = StateRegistry.get_metadata(state_code)
    if not metadata:
        # State not in registry, but might have data
        metadata = {"full_name": state_code}

    # Get hearing count
    hearing_count = db.query(func.count(Hearing.id)).filter(
        Hearing.state_code == state_code
    ).scalar() or 0

    return StateResponse(
        code=state_code,
        name=metadata.get("full_name", state_code),
        commission_name=metadata.get("commission_name"),
        hearing_count=hearing_count,
        docket_format=metadata.get("docket_format"),
    )
