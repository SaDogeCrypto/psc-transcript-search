# PSC Hearing Intelligence Platform - Multi-State Architecture

## Overview

A regulatory intelligence platform that processes Public Service Commission (PSC) hearings across multiple states. Each state has different data sources and document formats, but shares a common interface for transcription, analysis, and search.

## Directory Structure

```
psc-hearing-intelligence/
├── src/
│   ├── core/                      # Shared core functionality
│   │   ├── __init__.py
│   │   ├── config.py              # Configuration management
│   │   ├── database.py            # Database connection & session management
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # SQLAlchemy base, mixins
│   │   │   ├── docket.py          # Abstract docket model
│   │   │   ├── document.py        # Abstract document model
│   │   │   ├── hearing.py         # Abstract hearing model
│   │   │   ├── transcript.py      # Abstract transcript segment model
│   │   │   ├── analysis.py        # Abstract analysis model
│   │   │   └── entity.py          # Abstract entity model
│   │   ├── pipeline/
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # Abstract stage interface
│   │   │   ├── transcribe.py      # Whisper transcription (shared)
│   │   │   ├── analyze.py         # LLM analysis (shared)
│   │   │   └── orchestrator.py    # Pipeline runner
│   │   ├── scrapers/
│   │   │   ├── __init__.py
│   │   │   └── base.py            # Abstract scraper interface
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── storage.py         # Azure Blob / local file storage
│   │       └── search.py          # Full-text search service
│   │
│   ├── states/                    # State-specific implementations
│   │   ├── __init__.py
│   │   ├── registry.py            # State plugin registry
│   │   └── florida/
│   │       ├── __init__.py
│   │       ├── config.py          # FL-specific configuration
│   │       ├── models/
│   │       │   ├── __init__.py
│   │       │   ├── docket.py      # FLDocket (extends core)
│   │       │   ├── document.py    # FLDocument (Thunderstone)
│   │       │   ├── hearing.py     # FLHearing, FLTranscriptSegment
│   │       │   ├── analysis.py    # FLAnalysis
│   │       │   └── entity.py      # FLEntity
│   │       ├── scrapers/
│   │       │   ├── __init__.py
│   │       │   ├── clerk_office.py    # ClerkOffice API scraper
│   │       │   ├── thunderstone.py    # Thunderstone document scraper
│   │       │   └── rss_hearing.py     # RSS hearing feed scraper
│   │       └── pipeline/
│   │           ├── __init__.py
│   │           ├── docket_sync.py     # FL docket sync stage
│   │           └── document_sync.py   # FL document sync stage
│   │
│   └── api/                       # FastAPI application
│       ├── __init__.py
│       ├── main.py                # App factory
│       ├── dependencies.py        # Dependency injection
│       ├── routes/
│       │   ├── __init__.py
│       │   ├── dockets.py         # GET /api/dockets
│       │   ├── documents.py       # GET /api/documents
│       │   ├── hearings.py        # GET /api/hearings
│       │   ├── search.py          # GET /api/search
│       │   └── admin/
│       │       ├── __init__.py
│       │       ├── pipeline.py    # POST /api/admin/pipeline/*
│       │       └── scraper.py     # POST /api/admin/scraper/*
│       └── schemas/               # Pydantic request/response models
│           ├── __init__.py
│           ├── docket.py
│           ├── document.py
│           ├── hearing.py
│           └── pipeline.py
│
├── dashboard/                     # Next.js frontend
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx           # Dashboard home
│   │   │   ├── hearings/
│   │   │   │   ├── page.tsx       # Hearing list
│   │   │   │   └── [id]/page.tsx  # Hearing detail
│   │   │   ├── dockets/
│   │   │   │   ├── page.tsx       # Docket list
│   │   │   │   └── [id]/page.tsx  # Docket detail
│   │   │   ├── search/page.tsx    # Full-text search
│   │   │   └── admin/
│   │   │       ├── layout.tsx
│   │   │       └── pipeline/page.tsx
│   │   ├── components/
│   │   └── lib/
│   │       └── api.ts             # API client
│   └── package.json
│
├── migrations/                    # Alembic migrations
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│
├── scripts/                       # CLI tools
│   ├── run_scraper.py
│   ├── run_pipeline.py
│   └── migrate.py
│
├── tests/
│   ├── conftest.py
│   ├── test_api/
│   ├── test_pipeline/
│   └── test_scrapers/
│
├── docker-compose.yml             # Local development
├── Dockerfile                     # Production container
├── pyproject.toml
└── .github/
    └── workflows/
        └── deploy.yml             # CI/CD to Azure
```

---

## Database Schema

### Core Tables (Shared Interface)

All state-specific tables extend these base schemas.

```sql
-- Core docket interface (states extend this)
CREATE TABLE dockets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_code VARCHAR(2) NOT NULL,          -- 'FL', 'TX', 'CA', etc.
    docket_number VARCHAR(50) NOT NULL,       -- State-specific format
    title TEXT,
    description TEXT,
    status VARCHAR(50),                       -- open, closed, pending
    filed_date DATE,
    closed_date DATE,
    docket_type VARCHAR(100),

    -- Common metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(state_code, docket_number)
);

CREATE INDEX idx_dockets_state ON dockets(state_code);
CREATE INDEX idx_dockets_status ON dockets(status);
CREATE INDEX idx_dockets_filed_date ON dockets(filed_date);

-- Core document interface
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_code VARCHAR(2) NOT NULL,
    docket_id UUID REFERENCES dockets(id),

    title TEXT NOT NULL,
    document_type VARCHAR(100),
    filed_date DATE,
    file_url TEXT,
    file_size_bytes INTEGER,

    -- Full-text content (extracted)
    content_text TEXT,

    -- Source tracking
    source_system VARCHAR(50),                -- 'thunderstone', 'cms', etc.
    external_id VARCHAR(255),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_documents_docket ON documents(docket_id);
CREATE INDEX idx_documents_state ON documents(state_code);
CREATE INDEX idx_documents_type ON documents(document_type);

-- Core hearing interface
CREATE TABLE hearings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_code VARCHAR(2) NOT NULL,
    docket_id UUID REFERENCES dockets(id),
    docket_number VARCHAR(50),                -- Denormalized for queries

    title TEXT,
    hearing_type VARCHAR(100),
    hearing_date DATE,
    scheduled_time TIME,
    location TEXT,

    -- Media
    video_url TEXT,
    audio_url TEXT,
    duration_seconds INTEGER,

    -- Transcript
    full_text TEXT,
    word_count INTEGER,
    transcript_status VARCHAR(50),            -- pending, transcribed, analyzed

    -- Processing metadata
    whisper_model VARCHAR(50),
    processing_cost_usd DECIMAL(10, 4),
    processed_at TIMESTAMPTZ,

    -- Source tracking
    external_id VARCHAR(255),
    source_system VARCHAR(50),

    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_hearings_state ON hearings(state_code);
CREATE INDEX idx_hearings_docket ON hearings(docket_id);
CREATE INDEX idx_hearings_date ON hearings(hearing_date);
CREATE INDEX idx_hearings_status ON hearings(transcript_status);

-- Transcript segments (speaker-attributed)
CREATE TABLE transcript_segments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hearing_id UUID NOT NULL REFERENCES hearings(id) ON DELETE CASCADE,

    segment_index INTEGER NOT NULL,
    start_time FLOAT,
    end_time FLOAT,
    text TEXT NOT NULL,

    -- Speaker attribution
    speaker_label VARCHAR(50),                -- SPEAKER_01, etc.
    speaker_name VARCHAR(255),                -- Resolved name
    speaker_role VARCHAR(100),                -- commissioner, counsel, witness

    -- Embedding for semantic search
    embedding VECTOR(1536),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_segments_hearing ON transcript_segments(hearing_id);
CREATE INDEX idx_segments_speaker ON transcript_segments(speaker_name);

-- Analysis results
CREATE TABLE analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hearing_id UUID NOT NULL REFERENCES hearings(id) ON DELETE CASCADE,

    -- Executive summary
    summary TEXT,
    one_sentence_summary TEXT,

    -- Classification
    hearing_type VARCHAR(100),
    utility_name VARCHAR(255),
    sector VARCHAR(50),                       -- electric, gas, water, telecom

    -- Structured extractions (JSONB for flexibility)
    participants_json JSONB,
    issues_json JSONB,
    commitments_json JSONB,
    vulnerabilities_json JSONB,
    commissioner_concerns_json JSONB,
    risk_factors_json JSONB,
    action_items_json JSONB,
    quotes_json JSONB,
    topics_extracted JSONB,
    utilities_extracted JSONB,

    -- Commissioner sentiment
    commissioner_mood VARCHAR(50),

    -- Public comment
    public_comments TEXT,
    public_sentiment VARCHAR(50),

    -- Predictions
    likely_outcome TEXT,
    outcome_confidence FLOAT,
    confidence_score FLOAT,

    -- Processing metadata
    model VARCHAR(100),
    cost_usd DECIMAL(10, 4),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_analyses_hearing ON analyses(hearing_id);

-- Extracted entities with review workflow
CREATE TABLE entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    state_code VARCHAR(2) NOT NULL,
    hearing_id UUID REFERENCES hearings(id),
    analysis_id UUID REFERENCES analyses(id),

    entity_type VARCHAR(50) NOT NULL,         -- utility, person, docket, statute, etc.
    value TEXT NOT NULL,
    normalized_value TEXT,
    context TEXT,
    confidence FLOAT,

    -- Review workflow
    status VARCHAR(20) DEFAULT 'pending',     -- pending, verified, rejected
    reviewed_at TIMESTAMPTZ,
    reviewed_by VARCHAR(255),

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_entities_type ON entities(entity_type);
CREATE INDEX idx_entities_status ON entities(status);
CREATE INDEX idx_entities_hearing ON entities(hearing_id);
```

### Florida-Specific Extensions

```sql
-- Florida docket extensions
CREATE TABLE fl_docket_details (
    docket_id UUID PRIMARY KEY REFERENCES dockets(id) ON DELETE CASCADE,

    -- Florida docket format: YYYYNNNN-XX (year, sequence, sector)
    year INTEGER,
    sequence_number INTEGER,
    sector_code VARCHAR(10),                  -- EI, GU, WU, etc.

    -- Applicant/utility
    applicant_name TEXT,

    -- Rate case specific fields
    is_rate_case BOOLEAN DEFAULT FALSE,
    requested_revenue_increase DECIMAL(15, 2),
    approved_revenue_increase DECIMAL(15, 2),
    requested_roe DECIMAL(5, 3),              -- Return on equity
    approved_roe DECIMAL(5, 3),

    -- Commissioner assignments
    commissioner_assignments JSONB,           -- [{name, role, assigned_date}]

    -- Related dockets (array of docket numbers)
    related_dockets TEXT[],

    -- ClerkOffice API metadata
    clerk_office_id VARCHAR(100),
    clerk_office_data JSONB,
    last_synced_at TIMESTAMPTZ
);

CREATE INDEX idx_fl_docket_year ON fl_docket_details(year);
CREATE INDEX idx_fl_docket_sector ON fl_docket_details(sector_code);

-- Florida document extensions (Thunderstone)
CREATE TABLE fl_document_details (
    document_id UUID PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,

    -- Thunderstone-specific fields
    thunderstone_id VARCHAR(100),
    profile VARCHAR(50),                      -- library, filingsCurrent, orders, tariffs
    thunderstone_score FLOAT,

    -- Additional FL metadata
    filing_party TEXT,
    document_category VARCHAR(100)
);

CREATE INDEX idx_fl_doc_thunderstone ON fl_document_details(thunderstone_id);
CREATE INDEX idx_fl_doc_profile ON fl_document_details(profile);

-- Florida hearing extensions (YouTube RSS)
CREATE TABLE fl_hearing_details (
    hearing_id UUID PRIMARY KEY REFERENCES hearings(id) ON DELETE CASCADE,

    -- YouTube source
    youtube_video_id VARCHAR(50),
    youtube_channel_id VARCHAR(50),

    -- RSS metadata
    rss_guid TEXT,
    rss_published_at TIMESTAMPTZ
);

CREATE INDEX idx_fl_hearing_youtube ON fl_hearing_details(youtube_video_id);
```

---

## Core Interfaces

### Abstract Base Models

```python
# src/core/models/base.py
from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase
import uuid

class Base(DeclarativeBase):
    pass

class StateModel:
    """Mixin for state-specific models."""
    state_code = Column(String(2), nullable=False, index=True)

class TimestampMixin:
    """Mixin for created_at/updated_at."""
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

```python
# src/core/models/docket.py
from typing import Optional, List
from datetime import date
from sqlalchemy import Column, String, Text, Date
from sqlalchemy.dialects.postgresql import UUID
from .base import Base, StateModel, TimestampMixin
import uuid

class Docket(Base, StateModel, TimestampMixin):
    """Core docket model - extended by state implementations."""
    __tablename__ = "dockets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    docket_number = Column(String(50), nullable=False)
    title = Column(Text)
    description = Column(Text)
    status = Column(String(50))
    filed_date = Column(Date)
    closed_date = Column(Date)
    docket_type = Column(String(100))
```

### Abstract Pipeline Stage

```python
# src/core/pipeline/base.py
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Tuple, Any
from dataclasses import dataclass
from sqlalchemy.orm import Session

T = TypeVar('T')  # Model type (Hearing, Document, etc.)

@dataclass
class StageResult:
    """Result from pipeline stage execution."""
    success: bool
    data: dict = None
    error: str = ""
    cost_usd: float = 0.0
    model: str = ""

class PipelineStage(ABC, Generic[T]):
    """Abstract base class for pipeline stages."""

    name: str  # Stage identifier

    @abstractmethod
    def validate(self, item: T, db: Session) -> Tuple[bool, str]:
        """Check if item can be processed. Returns (can_process, reason)."""
        pass

    @abstractmethod
    def execute(self, item: T, db: Session) -> StageResult:
        """Execute stage on item. Returns result."""
        pass
```

### Abstract Scraper

```python
# src/core/scrapers/base.py
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ScraperResult:
    """Result from scraper execution."""
    success: bool
    items_found: int = 0
    items_created: int = 0
    items_updated: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

class Scraper(ABC):
    """Abstract base class for data scrapers."""

    name: str
    state_code: str

    @abstractmethod
    def scrape(self, **kwargs) -> ScraperResult:
        """Execute scrape operation."""
        pass

    @abstractmethod
    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Fetch single item by ID."""
        pass
```

---

## State Plugin System

### Registry

```python
# src/states/registry.py
from typing import Dict, Type, List, Optional
from src.core.scrapers.base import Scraper
from src.core.pipeline.base import PipelineStage

class StateRegistry:
    """Registry for state-specific implementations."""

    _scrapers: Dict[str, Dict[str, Type[Scraper]]] = {}
    _stages: Dict[str, Dict[str, Type[PipelineStage]]] = {}
    _configs: Dict[str, dict] = {}

    @classmethod
    def register_scraper(cls, state_code: str, name: str, scraper_class: Type[Scraper]):
        """Register a scraper for a state."""
        if state_code not in cls._scrapers:
            cls._scrapers[state_code] = {}
        cls._scrapers[state_code][name] = scraper_class

    @classmethod
    def register_stage(cls, state_code: str, name: str, stage_class: Type[PipelineStage]):
        """Register a pipeline stage for a state."""
        if state_code not in cls._stages:
            cls._stages[state_code] = {}
        cls._stages[state_code][name] = stage_class

    @classmethod
    def get_scraper(cls, state_code: str, name: str) -> Optional[Type[Scraper]]:
        """Get scraper class by state and name."""
        return cls._scrapers.get(state_code, {}).get(name)

    @classmethod
    def get_stage(cls, state_code: str, name: str) -> Optional[Type[PipelineStage]]:
        """Get pipeline stage by state and name."""
        return cls._stages.get(state_code, {}).get(name)

    @classmethod
    def get_available_states(cls) -> List[str]:
        """Get list of registered states."""
        return list(set(cls._scrapers.keys()) | set(cls._stages.keys()))

    @classmethod
    def get_state_scrapers(cls, state_code: str) -> List[str]:
        """Get available scrapers for a state."""
        return list(cls._scrapers.get(state_code, {}).keys())
```

### Florida Registration

```python
# src/states/florida/__init__.py
from src.states.registry import StateRegistry
from src.states.florida.scrapers.clerk_office import ClerkOfficeScraper
from src.states.florida.scrapers.thunderstone import ThunderstoneScraper
from src.states.florida.scrapers.rss_hearing import RSSHearingScraper
from src.states.florida.pipeline.docket_sync import FLDocketSyncStage
from src.states.florida.pipeline.document_sync import FLDocumentSyncStage

STATE_CODE = "FL"

# Register Florida scrapers
StateRegistry.register_scraper(STATE_CODE, "clerk_office", ClerkOfficeScraper)
StateRegistry.register_scraper(STATE_CODE, "thunderstone", ThunderstoneScraper)
StateRegistry.register_scraper(STATE_CODE, "rss_hearings", RSSHearingScraper)

# Register Florida pipeline stages
StateRegistry.register_stage(STATE_CODE, "docket_sync", FLDocketSyncStage)
StateRegistry.register_stage(STATE_CODE, "document_sync", FLDocumentSyncStage)

# Core stages (transcribe/analyze) are shared across states
# They're registered in src/core/pipeline/__init__.py
```

---

## Florida Implementation

### Docket Model

```python
# src/states/florida/models/docket.py
from sqlalchemy import Column, String, Integer, Boolean, Numeric, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from src.core.models.docket import Docket
from src.core.models.base import Base
import re

class FLDocketDetails(Base):
    """Florida-specific docket fields."""
    __tablename__ = "fl_docket_details"

    docket_id = Column(UUID(as_uuid=True), ForeignKey("dockets.id", ondelete="CASCADE"), primary_key=True)

    # Florida format: YYYYNNNN-XX
    year = Column(Integer)
    sequence_number = Column(Integer)
    sector_code = Column(String(10))  # EI, GU, WU, TL, WS, etc.

    applicant_name = Column(String(500))

    # Rate case fields
    is_rate_case = Column(Boolean, default=False)
    requested_revenue_increase = Column(Numeric(15, 2))
    approved_revenue_increase = Column(Numeric(15, 2))
    requested_roe = Column(Numeric(5, 3))
    approved_roe = Column(Numeric(5, 3))

    # Commissioner info
    commissioner_assignments = Column(JSONB)  # [{name, role, assigned_date}]

    # Related dockets
    related_dockets = Column(ARRAY(String))

    # ClerkOffice API sync
    clerk_office_id = Column(String(100))
    clerk_office_data = Column(JSONB)
    last_synced_at = Column(DateTime(timezone=True))

    # Relationship back to core docket
    docket = relationship("Docket", backref="fl_details")

    @staticmethod
    def parse_docket_number(docket_number: str) -> dict:
        """Parse FL docket format: YYYYNNNN-XX"""
        pattern = r'^(\d{4})(\d{4})-([A-Z]{2})$'
        match = re.match(pattern, docket_number)
        if match:
            return {
                "year": int(match.group(1)),
                "sequence_number": int(match.group(2)),
                "sector_code": match.group(3)
            }
        return {}

# Sector code meanings
FL_SECTOR_CODES = {
    "EI": "Electric",
    "GU": "Gas Utility",
    "WU": "Water Utility",
    "WS": "Water/Sewer",
    "TL": "Telecommunications",
    "TP": "Transportation Pipeline",
    "EC": "Electric Cogeneration",
    "EM": "Electric Miscellaneous",
}
```

### ClerkOffice Scraper

```python
# src/states/florida/scrapers/clerk_office.py
import httpx
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.orm import Session

from src.core.scrapers.base import Scraper, ScraperResult
from src.core.models.docket import Docket
from src.states.florida.models.docket import FLDocketDetails

logger = logging.getLogger(__name__)

CLERK_OFFICE_API = "https://www.psc.state.fl.us/api/ClerkOffice"

class ClerkOfficeScraper(Scraper):
    """Scrape dockets from Florida PSC ClerkOffice API."""

    name = "clerk_office"
    state_code = "FL"

    def __init__(self, db: Session):
        self.db = db
        self.client = httpx.Client(timeout=30.0)

    def scrape(self, year: Optional[int] = None, **kwargs) -> ScraperResult:
        """Scrape dockets, optionally filtered by year."""
        year = year or datetime.now().year

        try:
            # Fetch docket list from API
            response = self.client.get(
                f"{CLERK_OFFICE_API}/Dockets",
                params={"year": year}
            )
            response.raise_for_status()
            dockets_data = response.json()

            items_created = 0
            items_updated = 0
            errors = []

            for docket_data in dockets_data:
                try:
                    created = self._upsert_docket(docket_data)
                    if created:
                        items_created += 1
                    else:
                        items_updated += 1
                except Exception as e:
                    errors.append(f"Error processing {docket_data.get('docketNumber')}: {e}")

            self.db.commit()

            return ScraperResult(
                success=True,
                items_found=len(dockets_data),
                items_created=items_created,
                items_updated=items_updated,
                errors=errors
            )

        except Exception as e:
            logger.exception("ClerkOffice scrape failed")
            return ScraperResult(success=False, errors=[str(e)])

    def get_item(self, docket_number: str) -> Optional[Dict[str, Any]]:
        """Fetch single docket by number."""
        response = self.client.get(f"{CLERK_OFFICE_API}/Dockets/{docket_number}")
        if response.status_code == 200:
            return response.json()
        return None

    def _upsert_docket(self, data: dict) -> bool:
        """Insert or update docket. Returns True if created."""
        docket_number = data.get("docketNumber")

        # Check if exists
        existing = self.db.query(Docket).filter(
            Docket.state_code == "FL",
            Docket.docket_number == docket_number
        ).first()

        if existing:
            # Update
            existing.title = data.get("title")
            existing.status = data.get("status")
            existing.updated_at = datetime.utcnow()

            # Update FL details
            if existing.fl_details:
                existing.fl_details.clerk_office_data = data
                existing.fl_details.last_synced_at = datetime.utcnow()

            return False

        # Create new
        parsed = FLDocketDetails.parse_docket_number(docket_number)

        docket = Docket(
            state_code="FL",
            docket_number=docket_number,
            title=data.get("title"),
            status=data.get("status"),
            filed_date=data.get("filedDate"),
            docket_type=data.get("docketType")
        )
        self.db.add(docket)
        self.db.flush()  # Get ID

        fl_details = FLDocketDetails(
            docket_id=docket.id,
            year=parsed.get("year"),
            sequence_number=parsed.get("sequence_number"),
            sector_code=parsed.get("sector_code"),
            applicant_name=data.get("applicantName"),
            clerk_office_id=data.get("id"),
            clerk_office_data=data,
            last_synced_at=datetime.utcnow()
        )
        self.db.add(fl_details)

        return True
```

### Thunderstone Document Scraper

```python
# src/states/florida/scrapers/thunderstone.py
import httpx
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from src.core.scrapers.base import Scraper, ScraperResult
from src.core.models.document import Document
from src.states.florida.models.document import FLDocumentDetails

logger = logging.getLogger(__name__)

# Thunderstone search profiles
THUNDERSTONE_PROFILES = {
    "library": "https://www.psc.state.fl.us/library",
    "filingsCurrent": "https://www.psc.state.fl.us/filings/current",
    "orders": "https://www.psc.state.fl.us/orders",
    "tariffs": "https://www.psc.state.fl.us/tariffs"
}

class ThunderstoneScraper(Scraper):
    """Scrape documents from Florida PSC Thunderstone search."""

    name = "thunderstone"
    state_code = "FL"

    def __init__(self, db: Session):
        self.db = db
        self.client = httpx.Client(timeout=60.0)

    def scrape(
        self,
        docket_number: Optional[str] = None,
        profile: str = "library",
        max_results: int = 100,
        **kwargs
    ) -> ScraperResult:
        """Search Thunderstone for documents."""

        search_url = THUNDERSTONE_PROFILES.get(profile)
        if not search_url:
            return ScraperResult(success=False, errors=[f"Unknown profile: {profile}"])

        try:
            params = {
                "pr": profile,
                "max": max_results,
            }
            if docket_number:
                params["q"] = docket_number

            response = self.client.get(search_url, params=params)
            response.raise_for_status()

            # Parse Thunderstone XML/JSON response
            results = self._parse_response(response.text, profile)

            items_created = 0
            items_updated = 0
            errors = []

            for doc_data in results:
                try:
                    created = self._upsert_document(doc_data, profile)
                    if created:
                        items_created += 1
                    else:
                        items_updated += 1
                except Exception as e:
                    errors.append(f"Error: {e}")

            self.db.commit()

            return ScraperResult(
                success=True,
                items_found=len(results),
                items_created=items_created,
                items_updated=items_updated,
                errors=errors
            )

        except Exception as e:
            logger.exception("Thunderstone scrape failed")
            return ScraperResult(success=False, errors=[str(e)])

    def get_item(self, thunderstone_id: str) -> Optional[Dict[str, Any]]:
        """Fetch document by Thunderstone ID."""
        # Implementation depends on Thunderstone API
        pass

    def _parse_response(self, content: str, profile: str) -> list:
        """Parse Thunderstone search results."""
        # Thunderstone returns XML - parse into list of dicts
        # Implementation details depend on actual response format
        results = []
        # ... parsing logic ...
        return results

    def _upsert_document(self, data: dict, profile: str) -> bool:
        """Insert or update document."""
        thunderstone_id = data.get("id")

        existing_detail = self.db.query(FLDocumentDetails).filter(
            FLDocumentDetails.thunderstone_id == thunderstone_id
        ).first()

        if existing_detail:
            # Update existing
            doc = existing_detail.document
            doc.title = data.get("title")
            doc.updated_at = datetime.utcnow()
            return False

        # Create new document
        doc = Document(
            state_code="FL",
            title=data.get("title"),
            document_type=data.get("documentType"),
            filed_date=data.get("filedDate"),
            file_url=data.get("url"),
            source_system="thunderstone",
            external_id=thunderstone_id
        )
        self.db.add(doc)
        self.db.flush()

        fl_details = FLDocumentDetails(
            document_id=doc.id,
            thunderstone_id=thunderstone_id,
            profile=profile,
            thunderstone_score=data.get("score")
        )
        self.db.add(fl_details)

        return True
```

---

## Shared Pipeline Stages

### Transcribe Stage (Whisper)

```python
# src/core/pipeline/transcribe.py
import os
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass

from sqlalchemy.orm import Session
from src.core.pipeline.base import PipelineStage, StageResult
from src.core.models.hearing import Hearing
from src.core.models.transcript import TranscriptSegment

logger = logging.getLogger(__name__)

# Configuration
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

class TranscribeStage(PipelineStage[Hearing]):
    """Transcribe hearing audio using Whisper (Groq > Azure > OpenAI)."""

    name = "transcribe"

    def __init__(self, audio_dir: Optional[Path] = None):
        self.audio_dir = audio_dir or Path(os.getenv("AUDIO_DIR", "data/audio"))
        self._client = None
        self._provider = self._select_provider()

    def _select_provider(self) -> str:
        """Select best available Whisper provider."""
        if GROQ_API_KEY:
            return "groq"
        elif AZURE_OPENAI_ENDPOINT:
            return "azure"
        elif OPENAI_API_KEY:
            return "openai"
        return "none"

    def validate(self, hearing: Hearing, db: Session) -> Tuple[bool, str]:
        """Check if hearing can be transcribed."""
        if self._provider == "none":
            return False, "No Whisper API configured"

        audio_path = self._get_audio_path(hearing)
        if not audio_path or not audio_path.exists():
            return False, f"Audio file not found"

        # Check if already transcribed
        segment_count = db.query(TranscriptSegment).filter(
            TranscriptSegment.hearing_id == hearing.id
        ).count()
        if segment_count > 0:
            return False, "Already transcribed"

        return True, ""

    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """Transcribe audio and save segments."""
        can_process, reason = self.validate(hearing, db)
        if not can_process:
            return StageResult(success=False, error=reason)

        audio_path = self._get_audio_path(hearing)

        try:
            # Build context prompt based on state
            initial_prompt = self._build_prompt(hearing)

            # Transcribe using selected provider
            text, segments, cost = self._transcribe(audio_path, initial_prompt)

            # Save to database
            hearing.full_text = text
            hearing.word_count = len(text.split()) if text else 0
            hearing.transcript_status = "transcribed"
            hearing.processing_cost_usd = cost

            for i, seg in enumerate(segments):
                segment = TranscriptSegment(
                    hearing_id=hearing.id,
                    segment_index=i,
                    start_time=seg.get("start", 0),
                    end_time=seg.get("end", 0),
                    text=seg.get("text", "")
                )
                db.add(segment)

            db.commit()

            return StageResult(
                success=True,
                data={"segments": len(segments), "words": hearing.word_count},
                cost_usd=cost,
                model=self._provider
            )

        except Exception as e:
            logger.exception(f"Transcription error for hearing {hearing.id}")
            return StageResult(success=False, error=str(e))

    def _get_audio_path(self, hearing: Hearing) -> Optional[Path]:
        """Find audio file for hearing."""
        filename = hearing.external_id or f"hearing_{hearing.id}"
        filename = "".join(c for c in filename if c.isalnum() or c in "-_")

        for ext in [".mp3", ".m4a", ".wav", ".mp4"]:
            path = self.audio_dir / f"{filename}{ext}"
            if path.exists():
                return path
        return None

    def _build_prompt(self, hearing: Hearing) -> str:
        """Build Whisper initial_prompt with context."""
        prompts = {
            "FL": "Florida Public Service Commission hearing. FPSC, FPL, Duke Energy Florida, Tampa Electric.",
            "TX": "Public Utility Commission of Texas hearing. PUCT, ERCOT, Oncor, CenterPoint.",
            "CA": "California Public Utilities Commission hearing. CPUC, PG&E, SCE, SDG&E.",
        }
        return prompts.get(hearing.state_code, "Public utility commission hearing transcript.")

    def _transcribe(self, audio_path: Path, prompt: str) -> Tuple[str, List[Dict], float]:
        """Transcribe audio file. Returns (text, segments, cost)."""
        # Implementation calls appropriate provider
        # Returns full text, list of segment dicts, and cost in USD
        pass
```

### Analyze Stage (GPT-4o-mini)

```python
# src/core/pipeline/analyze.py
import os
import json
import logging
from typing import Tuple
from sqlalchemy.orm import Session

from src.core.pipeline.base import PipelineStage, StageResult
from src.core.models.hearing import Hearing
from src.core.models.analysis import Analysis

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", "gpt-4o-mini")

class AnalyzeStage(PipelineStage[Hearing]):
    """Analyze hearing transcript using GPT-4o-mini."""

    name = "analyze"

    def validate(self, hearing: Hearing, db: Session) -> Tuple[bool, str]:
        """Check if hearing can be analyzed."""
        if not OPENAI_API_KEY:
            return False, "No OpenAI API key configured"

        existing = db.query(Analysis).filter(Analysis.hearing_id == hearing.id).first()
        if existing:
            return False, "Already analyzed"

        if not hearing.full_text or len(hearing.full_text.strip()) < 100:
            return False, "No transcript or transcript too short"

        return True, ""

    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """Analyze transcript and save results."""
        can_process, reason = self.validate(hearing, db)
        if not can_process:
            return StageResult(success=False, error=reason)

        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY)

            # Build prompts (system + user with transcript)
            system_prompt = self._get_system_prompt(hearing.state_code)
            user_prompt = self._get_user_prompt(hearing)

            response = client.chat.completions.create(
                model=ANALYSIS_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
                max_tokens=4000
            )

            data = json.loads(response.choices[0].message.content)

            # Calculate cost
            cost = (
                (response.usage.prompt_tokens * 0.15 / 1_000_000) +
                (response.usage.completion_tokens * 0.60 / 1_000_000)
            )

            # Save analysis
            analysis = Analysis(
                hearing_id=hearing.id,
                summary=data.get("summary"),
                one_sentence_summary=data.get("one_sentence_summary"),
                hearing_type=data.get("hearing_type"),
                utility_name=data.get("utility_name"),
                sector=data.get("sector"),
                participants_json=data.get("participants"),
                issues_json=data.get("issues"),
                commitments_json=data.get("commitments"),
                commissioner_concerns_json=data.get("commissioner_concerns"),
                commissioner_mood=data.get("commissioner_mood"),
                likely_outcome=data.get("likely_outcome"),
                outcome_confidence=data.get("outcome_confidence"),
                model=ANALYSIS_MODEL,
                cost_usd=cost
            )
            db.add(analysis)

            hearing.transcript_status = "analyzed"
            db.commit()

            return StageResult(
                success=True,
                data={"analysis_id": str(analysis.id)},
                cost_usd=cost,
                model=ANALYSIS_MODEL
            )

        except Exception as e:
            logger.exception(f"Analysis error for hearing {hearing.id}")
            return StageResult(success=False, error=str(e))

    def _get_system_prompt(self, state_code: str) -> str:
        """Get state-appropriate system prompt."""
        # Could customize for each state's regulatory context
        return """You are a senior regulatory affairs analyst..."""

    def _get_user_prompt(self, hearing: Hearing) -> str:
        """Build analysis prompt with transcript."""
        return f"""Analyze this {hearing.state_code} PSC hearing...

        TRANSCRIPT:
        {hearing.full_text[:100000]}

        Return JSON with: summary, participants, issues, ..."""
```

---

## API Routes

### State-Aware Endpoints

```python
# src/api/routes/hearings.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID

from src.api.dependencies import get_db
from src.api.schemas.hearing import HearingResponse, HearingListResponse
from src.core.models.hearing import Hearing

router = APIRouter(prefix="/api/hearings", tags=["hearings"])

@router.get("", response_model=HearingListResponse)
def list_hearings(
    state: Optional[str] = Query(None, description="Filter by state code (FL, TX, CA)"),
    status: Optional[str] = Query(None, description="Filter by transcript status"),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    db: Session = Depends(get_db)
):
    """List hearings with optional filters."""
    query = db.query(Hearing)

    if state:
        query = query.filter(Hearing.state_code == state.upper())
    if status:
        query = query.filter(Hearing.transcript_status == status)

    total = query.count()
    hearings = query.order_by(Hearing.hearing_date.desc()).offset(offset).limit(limit).all()

    return HearingListResponse(
        items=[HearingResponse.from_orm(h) for h in hearings],
        total=total,
        limit=limit,
        offset=offset
    )

@router.get("/{hearing_id}", response_model=HearingResponse)
def get_hearing(hearing_id: UUID, db: Session = Depends(get_db)):
    """Get hearing by ID."""
    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()
    if not hearing:
        raise HTTPException(status_code=404, detail="Hearing not found")
    return HearingResponse.from_orm(hearing)
```

### Admin Pipeline Routes

```python
# src/api/routes/admin/pipeline.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

from src.api.dependencies import get_db, require_admin
from src.api.schemas.pipeline import PipelineRequest, PipelineStatus
from src.core.pipeline.orchestrator import PipelineOrchestrator
from src.states.registry import StateRegistry

router = APIRouter(prefix="/api/admin/pipeline", tags=["admin"])

@router.post("/run")
async def run_pipeline(
    request: PipelineRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin = Depends(require_admin)
):
    """Run pipeline stage on hearing(s)."""
    state_code = request.state_code
    stage_name = request.stage  # "transcribe", "analyze", etc.

    # Get stage (shared or state-specific)
    stage_class = StateRegistry.get_stage(state_code, stage_name)
    if not stage_class:
        # Try core stages
        from src.core.pipeline import TranscribeStage, AnalyzeStage
        stages = {"transcribe": TranscribeStage, "analyze": AnalyzeStage}
        stage_class = stages.get(stage_name)

    if not stage_class:
        raise HTTPException(status_code=400, detail=f"Unknown stage: {stage_name}")

    # Queue background processing
    orchestrator = PipelineOrchestrator(db)
    background_tasks.add_task(
        orchestrator.run_stage,
        stage_class=stage_class,
        hearing_ids=request.hearing_ids,
        state_code=state_code
    )

    return {"status": "queued", "stage": stage_name, "count": len(request.hearing_ids)}
```

---

## Configuration

### Environment Variables

```bash
# .env.example

# Database (Azure PostgreSQL or local)
DATABASE_URL=postgresql://user:pass@localhost:5432/psc_dev
# For Azure:
# DATABASE_URL=postgresql://user:pass@server.postgres.database.azure.com:5432/psc?sslmode=require

# Storage (Azure Blob or local)
STORAGE_TYPE=local  # or "azure"
AUDIO_DIR=data/audio
# For Azure:
# AZURE_STORAGE_CONNECTION_STRING=DefaultEndpointsProtocol=https;...
# AZURE_STORAGE_CONTAINER=audio

# Whisper transcription (priority order)
GROQ_API_KEY=gsk_...           # Fastest, cheapest
AZURE_OPENAI_ENDPOINT=         # Azure fallback
AZURE_OPENAI_API_KEY=
OPENAI_API_KEY=sk-...          # OpenAI fallback

# Analysis
ANALYSIS_MODEL=gpt-4o-mini

# State configuration
ACTIVE_STATES=FL               # Comma-separated: FL,TX,CA

# API
API_SECRET_KEY=change-me-in-production
ADMIN_API_KEY=admin-key-here
```

### Config Module

```python
# src/core/config.py
from pydantic_settings import BaseSettings
from typing import List, Optional
from functools import lru_cache

class Settings(BaseSettings):
    # Database
    database_url: str

    # Storage
    storage_type: str = "local"
    audio_dir: str = "data/audio"
    azure_storage_connection_string: Optional[str] = None
    azure_storage_container: str = "audio"

    # Whisper
    groq_api_key: Optional[str] = None
    azure_openai_endpoint: Optional[str] = None
    azure_openai_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Analysis
    analysis_model: str = "gpt-4o-mini"

    # States
    active_states: str = "FL"

    @property
    def active_state_list(self) -> List[str]:
        return [s.strip().upper() for s in self.active_states.split(",")]

    # API
    api_secret_key: str = "dev-secret"
    admin_api_key: str = "admin-key"

    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

---

## Deployment

### Docker Compose (Local Development)

```yaml
# docker-compose.yml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: psc
      POSTGRES_PASSWORD: psc_dev
      POSTGRES_DB: psc_dev
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://psc:psc_dev@db:5432/psc_dev
      STORAGE_TYPE: local
      AUDIO_DIR: /data/audio
    volumes:
      - ./data:/data
      - .:/app
    depends_on:
      - db
    command: uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload

  dashboard:
    build: ./dashboard
    ports:
      - "3000:3000"
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
    volumes:
      - ./dashboard:/app
      - /app/node_modules
    command: npm run dev

volumes:
  postgres_data:
```

### Dockerfile

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (ffmpeg for audio processing)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry install --no-dev

# Copy application
COPY src/ ./src/
COPY migrations/ ./migrations/

# Run
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### GitHub Actions (Deploy to Azure)

```yaml
# .github/workflows/deploy.yml
name: Deploy to Azure

on:
  push:
    branches: [main]

env:
  AZURE_CONTAINER_REGISTRY: pschearing.azurecr.io
  IMAGE_NAME: psc-api

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Login to Azure Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.AZURE_CONTAINER_REGISTRY }}
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}

      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.AZURE_CONTAINER_REGISTRY }}/${{ env.IMAGE_NAME }}:latest
            ${{ env.AZURE_CONTAINER_REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}

      - name: Deploy to Azure Container Apps
        uses: azure/container-apps-deploy-action@v1
        with:
          resource-group: psc-hearing-rg
          container-app-name: psc-api
          image: ${{ env.AZURE_CONTAINER_REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
```

---

## Adding a New State

To add support for a new state (e.g., Texas):

### 1. Create State Directory

```
src/states/texas/
├── __init__.py          # Register with StateRegistry
├── config.py            # TX-specific configuration
├── models/
│   ├── __init__.py
│   └── docket.py        # TXDocketDetails extensions
└── scrapers/
    ├── __init__.py
    └── puct_api.py      # PUCT API scraper
```

### 2. Define State Models

```python
# src/states/texas/models/docket.py
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from src.core.models.base import Base

class TXDocketDetails(Base):
    """Texas-specific docket fields."""
    __tablename__ = "tx_docket_details"

    docket_id = Column(UUID(as_uuid=True), ForeignKey("dockets.id"), primary_key=True)

    # Texas format: XXXXX (5-digit control number)
    control_number = Column(String(10))

    # PUCT-specific fields
    proceeding_type = Column(String(100))
    ercot_region = Column(String(50))
```

### 3. Implement Scrapers

```python
# src/states/texas/scrapers/puct_api.py
from src.core.scrapers.base import Scraper, ScraperResult

class PUCTScraper(Scraper):
    name = "puct"
    state_code = "TX"

    def scrape(self, **kwargs) -> ScraperResult:
        # Implement PUCT API scraping
        pass
```

### 4. Register State

```python
# src/states/texas/__init__.py
from src.states.registry import StateRegistry
from src.states.texas.scrapers.puct_api import PUCTScraper

StateRegistry.register_scraper("TX", "puct", PUCTScraper)
```

### 5. Add Migration

```sql
-- migrations/versions/xxx_add_texas.sql
CREATE TABLE tx_docket_details (
    docket_id UUID PRIMARY KEY REFERENCES dockets(id) ON DELETE CASCADE,
    control_number VARCHAR(10),
    proceeding_type VARCHAR(100),
    ercot_region VARCHAR(50)
);
```

### 6. Enable State

```bash
# .env
ACTIVE_STATES=FL,TX
```

---

## Summary

This architecture provides:

1. **Shared Core**: Common models, pipeline stages (transcribe/analyze), and API routes
2. **State Extensions**: Each state adds its own data sources, scrapers, and model extensions
3. **Plugin Registry**: Clean registration system for state-specific components
4. **Unified Interface**: Same API and dashboard work across all states
5. **Local + Cloud**: Docker Compose for local dev, Azure Container Apps for production
6. **CI/CD**: GitHub Actions automatically deploy to Azure on push to main

The Florida implementation is complete with:
- ClerkOffice API scraper (dockets)
- Thunderstone scraper (documents)
- RSS hearing scraper (YouTube hearings)
- All existing model fields preserved (rate case data, commissioner assignments, entities)
