"""
Analysis model - LLM analysis results for a hearing.

Stores structured intelligence extracted by GPT-4o-mini:
- Executive summary
- Participant identification
- Issue/topic extraction
- Commissioner sentiment
- Outcome predictions
- Action items
"""

import uuid
from typing import Optional, TYPE_CHECKING

from sqlalchemy import Column, String, Text, Float, Numeric, ForeignKey, Index, JSON
from sqlalchemy.orm import relationship, Mapped

from src.core.models.base import Base, TimestampMixin, GUID

if TYPE_CHECKING:
    from src.core.models.hearing import Hearing


class Analysis(Base, TimestampMixin):
    """
    LLM analysis results for a hearing transcript.

    Contains structured intelligence extracted by GPT-4o-mini
    or similar model.
    """

    __tablename__ = "analyses"

    id = Column(GUID(), primary_key=True, default=uuid.uuid4)

    # Parent hearing (one-to-one relationship)
    hearing_id = Column(
        GUID(),
        ForeignKey("hearings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Executive summary
    summary = Column(Text, comment="2-3 paragraph executive summary")
    one_sentence_summary = Column(
        Text,
        comment="Single sentence capturing key takeaway",
    )

    # Classification
    hearing_type = Column(
        String(100),
        comment="Refined hearing type based on content analysis",
    )
    utility_name = Column(
        String(255),
        comment="Primary utility involved",
    )
    sector = Column(
        String(50),
        comment="Sector: electric, gas, water, telecom, multi",
    )

    # Structured extractions (JSON for flexibility)
    participants_json = Column(
        JSON,
        comment='[{name, role, affiliation}]',
    )
    issues_json = Column(
        JSON,
        comment='[{issue, description}]',
    )
    commitments_json = Column(
        JSON,
        comment='[{commitment, by_whom, context}]',
    )
    vulnerabilities_json = Column(
        JSON,
        comment='["weakness or vulnerability exposed"]',
    )
    commissioner_concerns_json = Column(
        JSON,
        comment='[{commissioner, concern}]',
    )
    risk_factors_json = Column(
        JSON,
        comment='["risk or uncertainty"]',
    )
    action_items_json = Column(
        JSON,
        comment='["follow-up action needed"]',
    )
    quotes_json = Column(
        JSON,
        comment='[{speaker, quote, significance}]',
    )
    topics_extracted = Column(
        JSON,
        comment='[{name, relevance, sentiment, context}]',
    )
    utilities_extracted = Column(
        JSON,
        comment='[{name, aliases, role, context}]',
    )
    dockets_extracted = Column(
        JSON,
        comment='Docket numbers mentioned in hearing',
    )

    # Commissioner sentiment
    commissioner_mood = Column(
        String(50),
        comment="Overall mood: supportive, skeptical, hostile, neutral, mixed",
    )

    # Public comment
    public_comments = Column(Text, comment="Summary of public input")
    public_sentiment = Column(
        String(50),
        comment="Public sentiment: supportive, opposed, mixed, none",
    )

    # Predictions
    likely_outcome = Column(Text, comment="Predicted outcome and reasoning")
    outcome_confidence = Column(
        Float,
        comment="Confidence in outcome prediction (0-1)",
    )
    confidence_score = Column(
        Float,
        comment="Overall analysis confidence (0-1)",
    )

    # Processing metadata
    model = Column(String(100), comment="Model used for analysis")
    cost_usd = Column(Numeric(10, 4), comment="Analysis cost in USD")

    # Relationships
    hearing: Mapped["Hearing"] = relationship(
        "Hearing",
        back_populates="analysis",
    )

    # Indexes
    __table_args__ = (
        Index("ix_analyses_utility", "utility_name"),
        Index("ix_analyses_sector", "sector"),
    )

    def __repr__(self) -> str:
        return f"<Analysis({self.hearing_id})>"

    @property
    def participants(self) -> list:
        """Parsed participants list."""
        return self.participants_json or []

    @property
    def issues(self) -> list:
        """Parsed issues list."""
        return self.issues_json or []

    @property
    def topics(self) -> list:
        """Parsed topics list."""
        return self.topics_extracted or []

    @property
    def quotes(self) -> list:
        """Parsed notable quotes."""
        return self.quotes_json or []
