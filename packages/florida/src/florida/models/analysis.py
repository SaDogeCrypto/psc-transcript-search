"""
Florida Analysis model.

Represents LLM-generated analysis of hearing transcripts.
"""
from datetime import datetime
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from decimal import Decimal

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Float, Numeric, ForeignKey
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from florida.models.base import Base, JSONB

if TYPE_CHECKING:
    from florida.models.hearing import FLHearing


class FLAnalysis(Base):
    """
    LLM-generated analysis for a hearing.

    Contains executive summary, extracted entities, commissioner concerns,
    utility vulnerabilities, outcome predictions, and notable quotes.
    """
    __tablename__ = 'fl_analyses'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hearing_id: Mapped[int] = mapped_column(Integer, ForeignKey('fl_hearings.id', ondelete='CASCADE'), unique=True)

    # Executive summary
    summary: Mapped[Optional[str]] = mapped_column(Text)
    one_sentence_summary: Mapped[Optional[str]] = mapped_column(Text)

    # Classification
    hearing_type: Mapped[Optional[str]] = mapped_column(String(100))
    utility_name: Mapped[Optional[str]] = mapped_column(String(200))
    sector: Mapped[Optional[str]] = mapped_column(String(50))

    # Extracted entities (JSON)
    participants_json = Column(JSONB)
    issues_json = Column(JSONB)
    commitments_json = Column(JSONB)
    vulnerabilities_json = Column(JSONB)
    commissioner_concerns_json = Column(JSONB)
    commissioner_mood: Mapped[Optional[str]] = mapped_column(String(50))

    # Public input
    public_comments: Mapped[Optional[str]] = mapped_column(Text)
    public_sentiment: Mapped[Optional[str]] = mapped_column(String(50))

    # Outcome prediction
    likely_outcome: Mapped[Optional[str]] = mapped_column(Text)
    outcome_confidence: Mapped[Optional[float]] = mapped_column(Float)
    risk_factors_json = Column(JSONB)
    action_items_json = Column(JSONB)
    quotes_json = Column(JSONB)

    # Topics and utilities extracted
    topics_extracted = Column(JSONB)
    utilities_extracted = Column(JSONB)
    dockets_extracted = Column(JSONB)

    # Metadata
    model: Mapped[Optional[str]] = mapped_column(String(50))
    cost_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)

    # Timestamps
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    hearing: Mapped[Optional["FLHearing"]] = relationship("FLHearing", back_populates="analysis")

    def __repr__(self):
        return f"<FLAnalysis {self.id} for hearing {self.hearing_id}>"

    @property
    def participants(self) -> List[Dict[str, Any]]:
        """Get participants as list of dicts."""
        return self.participants_json or []

    @property
    def issues(self) -> List[Dict[str, Any]]:
        """Get issues as list of dicts."""
        return self.issues_json or []

    @property
    def commitments(self) -> List[Dict[str, Any]]:
        """Get commitments as list of dicts."""
        return self.commitments_json or []

    @property
    def vulnerabilities(self) -> List[str]:
        """Get vulnerabilities as list of strings."""
        return self.vulnerabilities_json or []

    @property
    def commissioner_concerns(self) -> List[Dict[str, Any]]:
        """Get commissioner concerns as list of dicts."""
        return self.commissioner_concerns_json or []

    @property
    def risk_factors(self) -> List[str]:
        """Get risk factors as list of strings."""
        return self.risk_factors_json or []

    @property
    def action_items(self) -> List[str]:
        """Get action items as list of strings."""
        return self.action_items_json or []

    @property
    def quotes(self) -> List[Dict[str, Any]]:
        """Get notable quotes as list of dicts."""
        return self.quotes_json or []

    @property
    def topics(self) -> List[Dict[str, Any]]:
        """Get extracted topics."""
        return self.topics_extracted or []

    @property
    def utilities(self) -> List[Dict[str, Any]]:
        """Get extracted utilities."""
        return self.utilities_extracted or []
