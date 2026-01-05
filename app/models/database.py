"""
SQLAlchemy ORM models for the PSC Transcript Search database.
"""
from datetime import datetime
import os
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, DateTime, Date,
    ForeignKey, Numeric, JSON
)
from sqlalchemy.orm import relationship

# Use JSONB and ARRAY for PostgreSQL, JSON for SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///")
if DATABASE_URL.startswith("sqlite"):
    JSONB = JSON
    # SQLite doesn't support ARRAY, use JSON instead
    def ARRAY(item_type):
        return JSON
else:
    from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from app.database import Base


class State(Base):
    __tablename__ = "states"

    id = Column(Integer, primary_key=True)
    code = Column(String(2), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    commission_name = Column(String(200))
    created_at = Column(DateTime, default=datetime.utcnow)

    sources = relationship("Source", back_populates="state")
    hearings = relationship("Hearing", back_populates="state")


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    state_id = Column(Integer, ForeignKey("states.id", ondelete="CASCADE"))
    name = Column(String(200), nullable=False)
    source_type = Column(String(50), nullable=False)
    url = Column(Text, nullable=False)
    config_json = Column(JSONB, default={})
    enabled = Column(Boolean, default=True)
    check_frequency_hours = Column(Integer, default=24)
    last_checked_at = Column(DateTime)
    last_hearing_at = Column(DateTime)
    status = Column(String(20), default="pending")
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    state = relationship("State", back_populates="sources")
    hearings = relationship("Hearing", back_populates="source")


class Hearing(Base):
    __tablename__ = "hearings"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="SET NULL"))
    state_id = Column(Integer, ForeignKey("states.id", ondelete="CASCADE"))
    external_id = Column(String(100))
    title = Column(Text, nullable=False)
    description = Column(Text)
    hearing_date = Column(Date)
    hearing_type = Column(String(100))
    utility_name = Column(String(200))
    docket_numbers = Column(ARRAY(Text))
    source_url = Column(Text)
    video_url = Column(Text)
    duration_seconds = Column(Integer)
    status = Column(String(20), default="discovered")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    state = relationship("State", back_populates="hearings")
    source = relationship("Source", back_populates="hearings")
    pipeline_jobs = relationship("PipelineJob", back_populates="hearing", cascade="all, delete-orphan")
    transcript = relationship("Transcript", back_populates="hearing", uselist=False, cascade="all, delete-orphan")
    segments = relationship("Segment", back_populates="hearing", cascade="all, delete-orphan")
    analysis = relationship("Analysis", back_populates="hearing", uselist=False, cascade="all, delete-orphan")


class PipelineJob(Base):
    __tablename__ = "pipeline_jobs"

    id = Column(Integer, primary_key=True)
    hearing_id = Column(Integer, ForeignKey("hearings.id", ondelete="CASCADE"))
    stage = Column(String(20), nullable=False)
    status = Column(String(20), default="pending")
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    cost_usd = Column(Numeric(10, 4))
    metadata_json = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    hearing = relationship("Hearing", back_populates="pipeline_jobs")


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True)
    hearing_id = Column(Integer, ForeignKey("hearings.id", ondelete="CASCADE"), unique=True)
    full_text = Column(Text)
    word_count = Column(Integer)
    model = Column(String(50))
    cost_usd = Column(Numeric(10, 4))
    created_at = Column(DateTime, default=datetime.utcnow)

    hearing = relationship("Hearing", back_populates="transcript")
    segments = relationship("Segment", back_populates="transcript", cascade="all, delete-orphan")


class Segment(Base):
    __tablename__ = "segments"

    id = Column(Integer, primary_key=True)
    hearing_id = Column(Integer, ForeignKey("hearings.id", ondelete="CASCADE"))
    transcript_id = Column(Integer, ForeignKey("transcripts.id", ondelete="CASCADE"))
    segment_index = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    speaker = Column(String(200))
    speaker_role = Column(String(100))
    # embedding handled separately (pgvector)
    created_at = Column(DateTime, default=datetime.utcnow)

    hearing = relationship("Hearing", back_populates="segments")
    transcript = relationship("Transcript", back_populates="segments")


class Analysis(Base):
    __tablename__ = "analyses"

    id = Column(Integer, primary_key=True)
    hearing_id = Column(Integer, ForeignKey("hearings.id", ondelete="CASCADE"), unique=True)

    summary = Column(Text)
    one_sentence_summary = Column(Text)
    hearing_type = Column(String(100))
    utility_name = Column(String(200))

    participants_json = Column(JSONB)
    issues_json = Column(JSONB)
    commitments_json = Column(JSONB)
    vulnerabilities_json = Column(JSONB)
    commissioner_concerns_json = Column(JSONB)
    commissioner_mood = Column(String(100))

    public_comments = Column(Text)
    public_sentiment = Column(String(50))

    likely_outcome = Column(Text)
    outcome_confidence = Column(Float)
    risk_factors_json = Column(JSONB)
    action_items_json = Column(JSONB)
    quotes_json = Column(JSONB)

    model = Column(String(50))
    cost_usd = Column(Numeric(10, 4))
    confidence_score = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    hearing = relationship("Hearing", back_populates="analysis")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime)
    status = Column(String(20), default="running")

    sources_checked = Column(Integer, default=0)
    new_hearings = Column(Integer, default=0)
    hearings_processed = Column(Integer, default=0)
    errors = Column(Integer, default=0)

    transcription_cost_usd = Column(Numeric(10, 4), default=0)
    analysis_cost_usd = Column(Numeric(10, 4), default=0)
    total_cost_usd = Column(Numeric(10, 4), default=0)

    details_json = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)


class AlertSubscription(Base):
    __tablename__ = "alert_subscriptions"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False)
    alert_type = Column(String(50), nullable=False)
    config_json = Column(JSONB, nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Docket(Base):
    __tablename__ = "dockets"

    id = Column(Integer, primary_key=True)
    state_id = Column(Integer, ForeignKey("states.id"))
    docket_number = Column(String(50), nullable=False)
    normalized_id = Column(String(60), unique=True, nullable=False)

    # Metadata
    docket_type = Column(String(50))
    company = Column(String(255))
    title = Column(String(500))
    description = Column(Text)

    # Rolling summary
    current_summary = Column(Text)
    status = Column(String(50), default="open")
    decision_expected = Column(Date)

    # Tracking
    first_seen_at = Column(DateTime, default=datetime.utcnow)
    last_mentioned_at = Column(DateTime)
    mention_count = Column(Integer, default=1)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    state = relationship("State")
    hearing_dockets = relationship("HearingDocket", back_populates="docket")


class HearingDocket(Base):
    __tablename__ = "hearing_dockets"

    hearing_id = Column(Integer, ForeignKey("hearings.id", ondelete="CASCADE"), primary_key=True)
    docket_id = Column(Integer, ForeignKey("dockets.id", ondelete="CASCADE"), primary_key=True)

    mention_summary = Column(Text)
    timestamps_json = Column(Text)  # JSON array

    created_at = Column(DateTime, default=datetime.utcnow)

    hearing = relationship("Hearing")
    docket = relationship("Docket", back_populates="hearing_dockets")


class UserWatchlist(Base):
    __tablename__ = "user_watchlist"

    user_id = Column(Integer, primary_key=True)
    docket_id = Column(Integer, ForeignKey("dockets.id", ondelete="CASCADE"), primary_key=True)
    notify_on_mention = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    docket = relationship("Docket")
