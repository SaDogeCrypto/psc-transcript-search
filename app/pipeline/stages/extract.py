"""
Extract Stage - Extracts docket numbers and generates embeddings.

This final pipeline stage:
1. Extracts docket numbers from transcript text
2. Creates/updates Docket records
3. Links hearings to dockets via HearingDocket junction
4. Optionally generates embeddings for semantic search

Supports:
- Azure OpenAI (if AZURE_OPENAI_ENDPOINT is set)
- OpenAI API (if OPENAI_API_KEY is set)
"""

import os
import re
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from sqlalchemy.orm import Session

from app.pipeline.stages.base import BaseStage, StageResult
from app.models.database import Hearing, Transcript, Segment, Docket, HearingDocket, State, PipelineJob

logger = logging.getLogger(__name__)

# Configuration
GENERATE_EMBEDDINGS = os.getenv("GENERATE_EMBEDDINGS", "false").lower() == "true"

# Azure OpenAI configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
AZURE_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")

# OpenAI configuration (fallback)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

# Embedding pricing (as of 2024)
EMBEDDING_COST_PER_1M_TOKENS = 0.02  # text-embedding-3-small


# Docket number patterns by state
DOCKET_PATTERNS = {
    # Generic patterns (work for most states)
    "generic": [
        r'\b(\d{2}-\d{3,6}(?:-[A-Z]{2,3})?)\b',  # e.g., 24-00123, 24-00123-EL
        r'\b([A-Z]\.\d{2}-\d{2}-\d{3,4})\b',  # e.g., A.24-01-001 (California)
        r'\b(Docket\s*(?:No\.?\s*)?[\d-]+)\b',  # e.g., Docket No. 123456
        r'\b(Case\s*(?:No\.?\s*)?[\d-]+)\b',  # e.g., Case No. 123456
    ],
    # State-specific patterns
    "GA": [
        r'\b(\d{5})\b',  # Georgia uses 5-digit dockets like 44160
        r'\b(Docket\s*(?:No\.?\s*)?\d{5})\b',
    ],
    "CA": [
        r'\b([A-Z]\.\d{2}-\d{2}-\d{3})\b',  # A.24-01-001, R.23-05-018
        r'\b(Application\s*\d{2}-\d{2}-\d{3})\b',
    ],
    "TX": [
        r'\b(\d{5})\b',  # Texas uses 5-digit dockets
        r'\b(Project\s*No\.?\s*\d{5})\b',
    ],
    "FL": [
        r'\b(\d{6,8}-[A-Z]{2})\b',  # e.g., 20240001-EI
        r'\b(Docket\s*(?:No\.?\s*)?\d{6,8}-[A-Z]{2})\b',
    ],
}


class ExtractStage(BaseStage):
    """Extract dockets and generate embeddings."""

    name = "extract"
    in_progress_status = "extracting"
    complete_status = "extracted"

    def __init__(self):
        self._openai_client = None
        self._use_azure = bool(AZURE_OPENAI_ENDPOINT)

    @property
    def openai_client(self):
        """Lazy load OpenAI client (Azure or standard)."""
        if self._openai_client is None and GENERATE_EMBEDDINGS:
            if self._use_azure:
                from openai import AzureOpenAI
                self._openai_client = AzureOpenAI(
                    azure_endpoint=AZURE_OPENAI_ENDPOINT,
                    api_key=AZURE_OPENAI_API_KEY,
                    api_version=AZURE_OPENAI_API_VERSION,
                )
                logger.info(f"Using Azure OpenAI for embeddings: {AZURE_OPENAI_ENDPOINT}")
            else:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                logger.info("Using OpenAI API for embeddings")
        return self._openai_client

    @property
    def embedding_model(self):
        """Get embedding model/deployment name."""
        return AZURE_EMBEDDING_DEPLOYMENT if self._use_azure else EMBEDDING_MODEL

    def validate(self, hearing: Hearing, db: Session) -> bool:
        """Check if transcript exists."""
        transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()

        if not transcript:
            logger.warning(f"No transcript found for hearing {hearing.id}")
            return False

        return True

    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """Extract dockets and optionally generate embeddings."""
        transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()
        if not transcript:
            return StageResult(
                success=False,
                error="No transcript found",
                should_retry=False
            )

        cost_usd = 0.0
        dockets_found = []

        try:
            # 1. Extract and link docket numbers
            state_code = hearing.state.code if hearing.state else None
            docket_numbers = self._extract_docket_numbers(transcript.full_text, state_code)

            for docket_num in docket_numbers:
                docket = self._get_or_create_docket(docket_num, hearing, db)
                if docket:
                    self._link_hearing_to_docket(hearing, docket, db)
                    dockets_found.append(docket.normalized_id)

            logger.info(f"Extracted {len(dockets_found)} dockets from hearing {hearing.id}")

            # 2. Optionally generate embeddings for segments
            if GENERATE_EMBEDDINGS:
                segments = db.query(Segment).filter(Segment.hearing_id == hearing.id).all()
                if segments:
                    embedding_cost = self._generate_embeddings(segments, db)
                    cost_usd += embedding_cost
                    logger.info(f"Generated embeddings for {len(segments)} segments, ${embedding_cost:.4f}")

            db.commit()

            return StageResult(
                success=True,
                output={
                    "dockets_found": len(dockets_found),
                    "docket_ids": dockets_found,
                    "embeddings_generated": GENERATE_EMBEDDINGS,
                },
                cost_usd=cost_usd
            )

        except Exception as e:
            logger.exception(f"Extract error for hearing {hearing.id}")
            return StageResult(
                success=False,
                error=f"Extract error: {str(e)}",
                should_retry=True
            )

    def _extract_docket_numbers(self, text: str, state_code: Optional[str] = None) -> List[str]:
        """Extract docket numbers from text using regex patterns."""
        docket_numbers = set()

        # Get patterns for this state plus generic patterns
        patterns = DOCKET_PATTERNS.get("generic", []).copy()
        if state_code and state_code in DOCKET_PATTERNS:
            patterns.extend(DOCKET_PATTERNS[state_code])

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                # Clean up the match
                docket = match.strip()
                # Skip very short matches (likely false positives)
                if len(docket) >= 4:
                    docket_numbers.add(docket)

        return list(docket_numbers)

    def _normalize_docket_id(self, docket_number: str, state_code: Optional[str]) -> str:
        """Create normalized ID for docket (e.g., GA-44160)."""
        # Remove common prefixes
        cleaned = re.sub(r'^(Docket|Case|Application|Project)\s*(No\.?\s*)?', '', docket_number, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        if state_code:
            return f"{state_code}-{cleaned}"
        return cleaned

    def _get_or_create_docket(self, docket_number: str, hearing: Hearing, db: Session) -> Optional[Docket]:
        """Get existing docket or create new one."""
        state_code = hearing.state.code if hearing.state else None
        normalized_id = self._normalize_docket_id(docket_number, state_code)

        # Check for existing
        docket = db.query(Docket).filter(Docket.normalized_id == normalized_id).first()

        if docket:
            # Update last mentioned
            docket.last_mentioned_at = datetime.now(timezone.utc)
            docket.mention_count = (docket.mention_count or 0) + 1
            return docket

        # Create new docket
        docket = Docket(
            state_id=hearing.state_id,
            docket_number=docket_number,
            normalized_id=normalized_id,
            first_seen_at=datetime.now(timezone.utc),
            last_mentioned_at=datetime.now(timezone.utc),
            mention_count=1,
        )
        db.add(docket)
        db.flush()

        logger.info(f"Created new docket: {normalized_id}")
        return docket

    def _link_hearing_to_docket(self, hearing: Hearing, docket: Docket, db: Session):
        """Create HearingDocket junction record if not exists."""
        existing = db.query(HearingDocket).filter(
            HearingDocket.hearing_id == hearing.id,
            HearingDocket.docket_id == docket.id
        ).first()

        if not existing:
            link = HearingDocket(
                hearing_id=hearing.id,
                docket_id=docket.id,
            )
            db.add(link)

    def _generate_embeddings(self, segments: List[Segment], db: Session) -> float:
        """Generate embeddings for segments using OpenAI."""
        if not self.openai_client:
            return 0.0

        import tiktoken
        encoder = tiktoken.encoding_for_model("gpt-4")

        total_tokens = 0
        batch_size = 100  # Process in batches

        for i in range(0, len(segments), batch_size):
            batch = segments[i:i + batch_size]
            texts = [seg.text for seg in batch if seg.text]

            if not texts:
                continue

            try:
                response = self.openai_client.embeddings.create(
                    model=self.embedding_model,
                    input=texts
                )

                # Store embeddings
                for j, embedding_data in enumerate(response.data):
                    if i + j < len(batch):
                        # Note: Actual storage would require pgvector column
                        # For now, just count the cost
                        pass

                total_tokens += response.usage.total_tokens

            except Exception as e:
                logger.warning(f"Embedding batch error: {e}")
                continue

        cost_usd = (total_tokens * EMBEDDING_COST_PER_1M_TOKENS) / 1_000_000
        return cost_usd

    def on_error(self, hearing: Hearing, job: PipelineJob, result: StageResult, db: Session):
        """Clean up partial extraction on error."""
        # Remove hearing-docket links created in this run
        # (We don't delete dockets themselves as they might be referenced elsewhere)
        db.query(HearingDocket).filter(HearingDocket.hearing_id == hearing.id).delete()
        db.commit()
        logger.info(f"Cleaned up partial extraction for hearing {hearing.id}")
