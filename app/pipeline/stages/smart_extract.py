"""
SmartExtract Stage - Regex-based docket extraction from transcripts.

Uses state-specific regex patterns and fuzzy matching against known dockets
to find docket references in transcripts with higher accuracy than LLM extraction.

This stage runs after Analyze and is the primary method for docket extraction.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from app.pipeline.stages.base import BaseStage, StageResult
from app.pipeline.smart_extraction import SmartExtractionPipeline, CandidateDocket
from app.models.database import (
    Hearing, Transcript, Docket, HearingDocket, KnownDocket
)

logger = logging.getLogger(__name__)


class SmartExtractStage(BaseStage):
    """Extract docket references from transcripts using regex + known docket matching."""

    name = "smart_extract"
    in_progress_status = "smart_extracting"
    complete_status = "smart_extracted"

    def validate(self, hearing: Hearing, db: Session) -> bool:
        """Check if transcript exists and hearing has been analyzed."""
        # Need transcript
        transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()
        if not transcript or not transcript.full_text:
            logger.warning(f"No transcript for hearing {hearing.id}")
            return False

        # Need state for pattern matching
        if not hearing.state:
            logger.warning(f"No state for hearing {hearing.id}")
            return False

        return True

    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """Extract docket references using smart extraction pipeline."""
        # Get transcript
        transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()
        if not transcript:
            return StageResult(
                success=False,
                error="No transcript found",
                should_retry=False
            )

        state_code = hearing.state.code if hearing.state else 'XX'

        try:
            # Clean up previous docket links from this stage
            self._cleanup_previous_dockets(hearing, db)

            # Combine hearing title with transcript for docket extraction
            # The title often contains the primary docket number
            text_to_process = f"HEARING TITLE: {hearing.title or ''}\n\n{transcript.full_text}"

            # Run smart extraction pipeline
            pipeline = SmartExtractionPipeline(db)
            candidates = pipeline.process_transcript(
                text=text_to_process,
                state_code=state_code,
                hearing_id=hearing.id
            )

            # Store candidates to extracted_dockets table (for review UI)
            counts = pipeline.store_candidates(candidates, hearing.id)

            # Create HearingDocket links for accepted/needs_review candidates
            link_stats = self._create_hearing_docket_links(hearing, candidates, db)

            # Update hearing metadata
            hearing.has_docket_references = link_stats['total'] > 0

            db.commit()

            logger.info(
                f"SmartExtract hearing {hearing.id}: "
                f"{len(candidates)} candidates, "
                f"{link_stats['linked']} linked ({link_stats['created']} new dockets), "
                f"{counts.get('accepted', 0)} accepted, "
                f"{counts.get('needs_review', 0)} need review, "
                f"{counts.get('rejected', 0)} rejected"
            )

            return StageResult(
                success=True,
                output={
                    'candidates_found': len(candidates),
                    'dockets_linked': link_stats['linked'],
                    'dockets_created': link_stats['created'],
                    'accepted': counts.get('accepted', 0),
                    'needs_review': counts.get('needs_review', 0),
                    'rejected': counts.get('rejected', 0),
                },
                cost_usd=0.0  # No API cost - regex only
            )

        except Exception as e:
            logger.exception(f"SmartExtract error for hearing {hearing.id}")
            return StageResult(
                success=False,
                error=f"SmartExtract error: {str(e)}",
                should_retry=True
            )

    def _cleanup_previous_dockets(self, hearing: Hearing, db: Session):
        """Remove previous docket extractions for re-processing."""
        from sqlalchemy import text

        # Delete from extracted_dockets table
        db.execute(text(
            "DELETE FROM extracted_dockets WHERE hearing_id = :hearing_id"
        ), {"hearing_id": hearing.id})

        # Delete HearingDocket links (but keep Docket records for history)
        deleted = db.query(HearingDocket).filter(
            HearingDocket.hearing_id == hearing.id
        ).delete()

        if deleted:
            logger.info(f"Cleaned up {deleted} previous docket links for hearing {hearing.id}")

    def _create_hearing_docket_links(
        self,
        hearing: Hearing,
        candidates: list[CandidateDocket],
        db: Session
    ) -> Dict[str, int]:
        """Create HearingDocket links for accepted/needs_review candidates."""
        stats = {'linked': 0, 'created': 0, 'total': 0}

        for candidate in candidates:
            # Skip rejected candidates
            if candidate.status == 'rejected':
                continue

            stats['total'] += 1

            # Get or create Docket record
            docket, created = self._get_or_create_docket(hearing, candidate, db)
            if not docket:
                continue

            if created:
                stats['created'] += 1

            # Create HearingDocket link
            existing = db.query(HearingDocket).filter(
                HearingDocket.hearing_id == hearing.id,
                HearingDocket.docket_id == docket.id
            ).first()

            if existing:
                # Update existing link
                existing.confidence_score = candidate.confidence
                existing.match_type = candidate.match_type
                existing.needs_review = True  # All dockets require manual review
                existing.review_reason = candidate.review_reason
                existing.context_summary = self._build_context_summary(candidate)
            else:
                # Create new link
                hd = HearingDocket(
                    hearing_id=hearing.id,
                    docket_id=docket.id,
                    confidence_score=candidate.confidence,
                    match_type=candidate.match_type,
                    needs_review=True,  # All dockets require manual review
                    review_reason=candidate.review_reason,
                    context_summary=self._build_context_summary(candidate),
                )
                db.add(hd)
                stats['linked'] += 1

        return stats

    def _get_or_create_docket(
        self,
        hearing: Hearing,
        candidate: CandidateDocket,
        db: Session
    ) -> tuple[Optional[Docket], bool]:
        """Get existing docket or create new one."""
        # Check for existing docket by normalized ID
        docket = db.query(Docket).filter(
            Docket.normalized_id == candidate.normalized_id
        ).first()

        if docket:
            # Update last mentioned
            docket.last_mentioned_at = datetime.now(timezone.utc)
            docket.mention_count = (docket.mention_count or 0) + 1
            return docket, False

        # Create new docket
        docket = Docket(
            state_id=hearing.state_id,
            docket_number=candidate.raw_text,
            normalized_id=candidate.normalized_id,
            first_seen_at=datetime.now(timezone.utc),
            last_mentioned_at=datetime.now(timezone.utc),
            mention_count=1,
            confidence=self._map_status_to_confidence(candidate.status),
            match_score=candidate.fuzzy_score / 100.0 if candidate.fuzzy_score else None,
        )

        # Link to known docket if matched
        if candidate.matched_docket_id:
            docket.known_docket_id = candidate.matched_docket_id
            docket.title = candidate.matched_docket_title
            # Get additional info from known docket
            known = db.query(KnownDocket).get(candidate.matched_docket_id)
            if known:
                docket.company = known.utility_name
                docket.sector = known.sector

        db.add(docket)
        db.flush()

        logger.info(f"Created docket: {candidate.normalized_id} (confidence={candidate.confidence})")
        return docket, True

    def _map_status_to_confidence(self, status: str) -> str:
        """Map candidate status to docket confidence level."""
        mapping = {
            'accepted': 'verified',
            'needs_review': 'possible',
            'rejected': 'unverified',
        }
        return mapping.get(status, 'unverified')

    def _build_context_summary(self, candidate: CandidateDocket) -> str:
        """Build a context summary from candidate data including transcript snippet."""
        parts = []

        # Include transcript context (surrounding text where docket was found)
        transcript_context = ""
        if candidate.context_before or candidate.context_after:
            before = candidate.context_before[-100:] if candidate.context_before else ""
            after = candidate.context_after[:100] if candidate.context_after else ""
            transcript_context = f"...{before}[{candidate.raw_text}]{after}..."
            parts.append(f"Transcript: \"{transcript_context}\"")

        if candidate.trigger_phrase:
            parts.append(f"Found via: {candidate.trigger_phrase}")

        if candidate.matched_docket_title:
            parts.append(f"Match: {candidate.matched_docket_title}")

        if candidate.context_clues:
            parts.append(f"Clues: {', '.join(candidate.context_clues[:3])}")

        if candidate.suggested_correction:
            parts.append(f"Suggested: {candidate.suggested_correction}")

        return "; ".join(parts) if parts else None
