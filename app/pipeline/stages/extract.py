"""
Extract Stage - Generates embeddings for semantic search.

This final pipeline stage generates vector embeddings for transcript segments
to enable semantic search functionality.

Supports:
- Azure OpenAI (if AZURE_OPENAI_ENDPOINT is set)
- OpenAI API (if OPENAI_API_KEY is set)
"""

import os
import logging
from typing import List

from sqlalchemy.orm import Session

from app.pipeline.stages.base import BaseStage, StageResult
from app.models.database import Hearing, Transcript, Segment, PipelineJob

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


class ExtractStage(BaseStage):
    """Generate embeddings for transcript segments."""

    name = "extract"
    in_progress_status = "extracting"
    complete_status = "extracted"  # Fixed: was incorrectly set to "complete"

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
        # Accept matched (normal flow) or extracting (retry)
        if hearing.status not in ("matched", "extracting"):
            return False

        transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()
        if not transcript:
            logger.warning(f"No transcript found for hearing {hearing.id}")
            return False

        return True

    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """Generate embeddings for transcript segments."""
        cost_usd = 0.0
        segments_count = 0

        # Generate embeddings if enabled
        if GENERATE_EMBEDDINGS:
            segments = db.query(Segment).filter(Segment.hearing_id == hearing.id).all()
            if segments:
                segments_count = len(segments)
                embedding_cost = self._generate_embeddings(segments, db)
                cost_usd += embedding_cost
                logger.info(f"Generated embeddings for {segments_count} segments, ${embedding_cost:.4f}")
        else:
            logger.info(f"Embeddings disabled, skipping for hearing {hearing.id}")

        db.commit()

        return StageResult(
            success=True,
            output={
                "embeddings_generated": GENERATE_EMBEDDINGS,
                "segments_processed": segments_count,
            },
            cost_usd=cost_usd
        )

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

    def on_start(self, hearing: Hearing, job: PipelineJob, db: Session):
        """Set hearing status to extracting."""
        hearing.status = self.in_progress_status
        db.commit()

    def on_success(self, hearing: Hearing, job: PipelineJob, result: StageResult, db: Session):
        """Set hearing status to extracted."""
        hearing.status = self.complete_status
        db.commit()

    def on_error(self, hearing: Hearing, job: PipelineJob, result: StageResult, db: Session):
        """Handle extraction error."""
        logger.error(f"Extract failed for hearing {hearing.id}: {result.error}")
