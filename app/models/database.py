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
    # Pipeline tracking
    processing_started_at = Column(DateTime)
    processing_cost_usd = Column(Numeric(10, 4), default=0)
    # Entity linking (new)
    sector = Column(String(20))  # 'electric', 'gas', 'water', 'telecom', 'multi'
    primary_utility_id = Column(Integer, ForeignKey("utilities.id"))
    has_docket_references = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    state = relationship("State", back_populates="hearings")
    source = relationship("Source", back_populates="hearings")
    pipeline_jobs = relationship("PipelineJob", back_populates="hearing", cascade="all, delete-orphan")
    transcript = relationship("Transcript", back_populates="hearing", uselist=False, cascade="all, delete-orphan")
    segments = relationship("Segment", back_populates="hearing", cascade="all, delete-orphan")
    analysis = relationship("Analysis", back_populates="hearing", uselist=False, cascade="all, delete-orphan")
    # Entity linking relationships
    hearing_topics = relationship("HearingTopic", back_populates="hearing", cascade="all, delete-orphan")
    hearing_utilities = relationship("HearingUtility", back_populates="hearing", cascade="all, delete-orphan")
    primary_utility = relationship("Utility", foreign_keys=[primary_utility_id])


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
    sector = Column(String(20))  # 'electric', 'gas', 'water', 'telecom', 'multi'

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

    # Entity extraction results (new)
    topics_extracted = Column(JSONB)  # [{name, relevance, sentiment, context}]
    utilities_extracted = Column(JSONB)  # [{name, aliases, role, context}]
    dockets_extracted = Column(JSONB)  # [{number, context}]

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


class KnownDocket(Base):
    """Authoritative docket data scraped directly from PSC websites."""
    __tablename__ = "known_dockets"

    id = Column(Integer, primary_key=True)

    # Identity
    state_code = Column(String(2), nullable=False)
    docket_number = Column(String(50), nullable=False)
    normalized_id = Column(String(60), unique=True, nullable=False)

    # Parsed components
    year = Column(Integer)
    case_number = Column(Integer)
    suffix = Column(String(10))
    sector = Column(String(20))  # Legacy field, use utility_type instead

    # Core metadata (standardized across states)
    title = Column(Text)
    description = Column(Text)
    utility_name = Column(String(200))
    utility_type = Column(String(50))  # Electric, Gas, Water, Telephone, Multi
    industry = Column(String(50))  # Alternative name (used by GA)
    filing_party = Column(String(300))  # Who filed (may differ from utility)

    # Dates
    filing_date = Column(Date)
    decision_date = Column(Date)
    last_activity_date = Column(Date)

    # Classification
    status = Column(String(50))  # open, closed, pending
    docket_type = Column(String(100))  # Rate Case, Merger, Certificate, Complaint, Rulemaking
    sub_type = Column(String(100))  # More specific categorization
    case_type = Column(String(100))  # Legacy field

    # People
    assigned_commissioner = Column(String(200))
    assigned_judge = Column(String(200))  # ALJ/Hearing Examiner

    # Related data (stored as JSON for flexibility)
    related_dockets = Column(JSONB, default=[])
    parties = Column(JSONB, default=[])  # [{name, role}, ...]
    extra_data = Column(JSONB, default={})  # State-specific fields

    # Documents
    documents_url = Column(String(500))
    documents_count = Column(Integer)

    # Financial (for rate cases)
    amount_requested = Column(Numeric(15, 2))
    amount_approved = Column(Numeric(15, 2))
    decision_summary = Column(Text)

    # Source tracking
    source_url = Column(String(500))
    scraped_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Verification status
    verification_status = Column(String(20), default='unverified')  # unverified, verified, stale
    verified_at = Column(DateTime)


class DocketSource(Base):
    """Track which states have docket scrapers enabled."""
    __tablename__ = "docket_sources"

    id = Column(Integer, primary_key=True)
    state_code = Column(String(2), unique=True, nullable=False)
    state_name = Column(String(100), nullable=False)
    commission_name = Column(String(200))
    search_url = Column(String(500))
    scraper_type = Column(String(50))  # 'html_table', 'api_json', 'aspx_form'
    enabled = Column(Boolean, default=True)
    last_scraped_at = Column(DateTime)
    last_scrape_count = Column(Integer)
    last_error = Column(Text)
    scrape_frequency_hours = Column(Integer, default=168)  # Weekly
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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

    # Authoritative matching
    known_docket_id = Column(Integer, ForeignKey("known_dockets.id"))
    confidence = Column(String(20), default="unverified")  # verified, likely, possible, unverified
    match_score = Column(Float)
    sector = Column(String(20))
    year = Column(Integer)

    # Review workflow
    review_status = Column(String(20), default="pending")  # 'pending', 'reviewed', 'invalid', 'needs_review'
    reviewed_by = Column(String(100))
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    original_extracted = Column(Text)  # Store original before correction

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    state = relationship("State")
    known_docket = relationship("KnownDocket")
    hearing_dockets = relationship("HearingDocket", back_populates="docket")


class HearingDocket(Base):
    __tablename__ = "hearing_dockets"

    hearing_id = Column(Integer, ForeignKey("hearings.id", ondelete="CASCADE"), primary_key=True)
    docket_id = Column(Integer, ForeignKey("dockets.id", ondelete="CASCADE"), primary_key=True)

    mention_summary = Column(Text)
    timestamps_json = Column(Text)  # JSON array
    context_summary = Column(Text)  # Context from analysis

    # Smart validation
    confidence_score = Column(Integer)  # 0-100 smart validation score
    match_type = Column(String(20))  # 'exact', 'fuzzy', 'none'

    # Review workflow
    needs_review = Column(Boolean, default=False)
    review_reason = Column(Text)  # Why review is needed
    review_notes = Column(Text)

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


class PipelineSchedule(Base):
    """Database-backed schedule for automated pipeline/scraper runs."""
    __tablename__ = "pipeline_schedules"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    schedule_type = Column(String(20), nullable=False)  # 'interval', 'daily', 'cron'
    schedule_value = Column(String(100), nullable=False)  # '30m', '08:00', '0 */4 * * *'
    target = Column(String(50), nullable=False)  # 'scraper', 'pipeline', 'all'
    enabled = Column(Boolean, default=True)
    config_json = Column(JSON, default={})  # {states: [], max_cost: 50, only_stage: null}
    last_run_at = Column(DateTime)
    next_run_at = Column(DateTime)
    last_run_status = Column(String(20))  # 'success', 'error'
    last_run_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PipelineState(Base):
    """Singleton table tracking current orchestrator state."""
    __tablename__ = "pipeline_state"

    id = Column(Integer, primary_key=True)  # Always 1 (singleton)
    status = Column(String(20), default="idle")  # 'idle', 'running', 'paused', 'stopping'
    started_at = Column(DateTime)
    current_hearing_id = Column(Integer, ForeignKey("hearings.id"))
    current_stage = Column(String(30))
    hearings_processed = Column(Integer, default=0)
    errors_count = Column(Integer, default=0)
    total_cost_usd = Column(Numeric(10, 4), default=0)
    last_error = Column(Text)
    config_json = Column(JSON, default={})  # {states: [], max_cost: 50, only_stage: null}
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    current_hearing = relationship("Hearing")


# ============================================================================
# ENTITY MATCHING SYSTEM - Topics, Utilities, and Review Workflow
# ============================================================================

class Topic(Base):
    """Predefined and discovered topics for entity matching."""
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    category = Column(String(50))  # 'policy', 'technical', 'regulatory', 'consumer', 'uncategorized'
    description = Column(Text)
    mention_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    hearing_topics = relationship("HearingTopic", back_populates="topic")


class HearingTopic(Base):
    """Junction table linking hearings to topics."""
    __tablename__ = "hearing_topics"

    id = Column(Integer, primary_key=True)
    hearing_id = Column(Integer, ForeignKey("hearings.id", ondelete="CASCADE"))
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"))
    relevance_score = Column(Float)  # 0-1, how central to hearing
    mention_count = Column(Integer, default=1)
    context_summary = Column(Text)
    sentiment = Column(String(20))  # 'positive', 'negative', 'neutral', 'mixed'
    confidence = Column(String(20), default="auto")  # 'auto', 'verified', 'manual'
    confidence_score = Column(Integer)  # 0-100 smart validation score
    match_type = Column(String(20))  # 'exact', 'fuzzy', 'none'
    needs_review = Column(Boolean, default=False)
    review_reason = Column(Text)  # Why review is needed
    review_notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    hearing = relationship("Hearing", back_populates="hearing_topics")
    topic = relationship("Topic", back_populates="hearing_topics")


class Utility(Base):
    """Normalized utility/company entities."""
    __tablename__ = "utilities"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    normalized_name = Column(String(200), unique=True, nullable=False)
    aliases = Column(JSONB, default=[])  # ["FPL", "Florida Power and Light"]
    parent_company = Column(String(200))
    utility_type = Column(String(50))  # 'IOU', 'cooperative', 'municipal', 'regulatory'
    sectors = Column(JSONB, default=[])  # ['electric', 'gas']
    states = Column(JSONB, default=[])  # ['FL', 'GA']
    website = Column(String(500))
    mention_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    hearing_utilities = relationship("HearingUtility", back_populates="utility")


class HearingUtility(Base):
    """Junction table linking hearings to utilities."""
    __tablename__ = "hearing_utilities"

    id = Column(Integer, primary_key=True)
    hearing_id = Column(Integer, ForeignKey("hearings.id", ondelete="CASCADE"))
    utility_id = Column(Integer, ForeignKey("utilities.id", ondelete="CASCADE"))
    role = Column(String(50))  # 'applicant', 'intervenor', 'subject'
    context_summary = Column(Text)
    confidence = Column(String(20), default="auto")
    confidence_score = Column(Integer)  # 0-100 smart validation score
    match_type = Column(String(20))  # 'exact', 'fuzzy', 'none'
    needs_review = Column(Boolean, default=False)
    review_reason = Column(Text)  # Why review is needed
    review_notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    hearing = relationship("Hearing", back_populates="hearing_utilities")
    utility = relationship("Utility", back_populates="hearing_utilities")


class EntityCorrection(Base):
    """Track manual corrections for training and improvement."""
    __tablename__ = "entity_corrections"

    id = Column(Integer, primary_key=True)
    entity_type = Column(String(20), nullable=False)  # 'docket', 'topic', 'utility'
    hearing_id = Column(Integer, ForeignKey("hearings.id"))

    # What was extracted vs corrected
    original_text = Column(Text, nullable=False)
    original_entity_id = Column(Integer)
    corrected_text = Column(Text)
    correct_entity_id = Column(Integer)

    correction_type = Column(String(50))  # 'typo', 'wrong_entity', 'merge', 'split', 'invalid', 'new'
    transcript_context = Column(Text)

    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    hearing = relationship("Hearing")


class StatePSCConfig(Base):
    """Configuration for each state PSC scraper including URLs and field mappings."""
    __tablename__ = "state_psc_configs"

    id = Column(Integer, primary_key=True)
    state_code = Column(String(2), unique=True, nullable=False)
    state_name = Column(String(100), nullable=False)
    commission_name = Column(String(200))
    commission_abbreviation = Column(String(20))

    # URLs
    website_url = Column(String(500))
    docket_search_url = Column(String(500))
    docket_detail_url_template = Column(String(500))  # e.g., "https://psc.ga.gov/...?docketId={docket}"
    documents_url_template = Column(String(500))

    # Scraper configuration
    scraper_type = Column(String(50))  # html, api, aspx, js_rendered
    requires_session = Column(Boolean, default=False)
    rate_limit_ms = Column(Integer, default=1000)

    # Field mappings (how to extract data from pages)
    field_mappings = Column(JSONB, default={})

    # Docket format info
    docket_format_regex = Column(String(200))
    docket_format_example = Column(String(50))

    # Status
    enabled = Column(Boolean, default=False)
    last_scrape_at = Column(DateTime)
    last_error = Column(Text)
    dockets_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DocketVerification(Base):
    """History of verification attempts for dockets."""
    __tablename__ = "docket_verifications"

    id = Column(Integer, primary_key=True)
    docket_id = Column(Integer, ForeignKey("known_dockets.id", ondelete="CASCADE"))
    extraction_id = Column(Integer)  # If verified from an extraction
    state_code = Column(String(2), nullable=False)
    docket_number = Column(String(50), nullable=False)

    # Verification result
    verified = Column(Boolean, nullable=False)
    source_url = Column(String(500))

    # Scraped data
    scraped_title = Column(Text)
    scraped_utility_type = Column(String(50))
    scraped_company = Column(String(300))
    scraped_filing_date = Column(Date)
    scraped_status = Column(String(50))
    scraped_metadata = Column(JSONB, default={})

    # Tracking
    verified_at = Column(DateTime, default=datetime.utcnow)
    error_message = Column(Text)

    # Relationship
    docket = relationship("KnownDocket")
