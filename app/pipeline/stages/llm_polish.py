"""
LLM Polish Stage - Targeted LLM correction for suspicious transcript segments.

Instead of sending the entire transcript to an LLM (expensive), this stage:
1. Identifies segments with potential transcription errors
2. Sends only those segments to GPT-4o-mini for correction
3. Merges corrections back into the transcript

Cost: ~$0.01-0.02 per transcript (vs $0.10+ for full transcript)
"""

import os
import re
import json
import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.pipeline.stages.base import BaseStage, StageResult
from app.models.database import Hearing, Transcript, Segment

logger = logging.getLogger(__name__)

# Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LLM_POLISH_MODEL = os.getenv("LLM_POLISH_MODEL", "gpt-4o-mini")
MAX_SEGMENTS_TO_POLISH = 50  # Limit to control costs
LLM_POLISH_COST_PER_1K_TOKENS = 0.00015  # GPT-4o-mini input price


@dataclass
class FlaggedSegment:
    """A segment flagged for LLM review."""
    segment_id: int
    segment_index: int
    text: str
    reason: str
    context_before: str = ""
    context_after: str = ""


# Patterns that suggest transcription errors
SUSPICIOUS_PATTERNS = [
    # Numbers that might be docket numbers but look garbled
    (r'\b(?:five|six|seven|eight|nine)\s+(?:thought|dot|dash)\s+\d+', "number words as docket"),
    (r'\bdocu(?:ment)?\s+number\b', "garbled docket"),

    # Common Whisper mishearings - utility/regulatory terms
    (r'\b(?:killer|killa)\s+(?:one|once|watts?)\b', "kilowatt mishearing"),
    (r'\b(?:mega)\s*(?:hertz|hurts)\b', "megawatt mishearing"),
    (r'\b(?:air|er)\s*(?:cot|caught|kot)\b', "ERCOT mishearing"),
    (r'\b(?:see|sea)\s*(?:puck|pack)\b', "CPUC mishearing"),
    (r'\bp\s*u\s*c\s*[ot]\b', "PUCO/PUCT mishearing"),
    (r'\bf\s*p\s*[sl]\s*c\b', "FPSC mishearing"),
    (r'\bo\s*c\s*g\s*a\b', "OCGA mishearing"),

    # Company name mishearings
    (r'\b(?:george|gorge)\s+power\b', "Georgia Power mishearing"),
    (r'\b(?:on|encore)\s+core?\b', "Oncor mishearing"),
    (r'\bcenter\s+point\b', "CenterPoint mishearing"),
    (r'\bpg\s+and\s+e\b', "PG&E mishearing"),

    # Placeholder/quality issues
    (r'\binaudible\b', "inaudible marker"),
    (r'\b(?:um|uh)\s+(?:um|uh)\s+(?:um|uh)\b', "excessive filler words"),
    (r'(\b\w{4,}\b)\s+\1\s+\1', "triple word repetition"),

    # Unusual punctuation from Whisper
    (r'\.{4,}', "excessive ellipsis"),
    (r'\?\s*\?\s*\?', "triple question marks"),
]


class LLMPolishStage(BaseStage):
    """Polish transcript segments using targeted LLM correction."""

    name = "llm_polish"
    in_progress_status = "polishing"
    complete_status = "polished"

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """Lazy load OpenAI client."""
        if self._client is None and OPENAI_API_KEY:
            from openai import OpenAI
            self._client = OpenAI(api_key=OPENAI_API_KEY)
        return self._client

    def validate(self, hearing: Hearing, db: Session) -> bool:
        """Check if transcript exists and has segments."""
        if not OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not set - skipping LLM polish")
            return False

        transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()
        if not transcript:
            logger.warning(f"No transcript for hearing {hearing.id}")
            return False

        segments = db.query(Segment).filter(Segment.hearing_id == hearing.id).count()
        if segments == 0:
            logger.warning(f"No segments for hearing {hearing.id}")
            return False

        return True

    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """Identify and polish suspicious segments."""
        transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()
        segments = db.query(Segment).filter(
            Segment.hearing_id == hearing.id
        ).order_by(Segment.segment_index).all()

        if not segments:
            return StageResult(success=True, output={"skipped": "no segments"})

        try:
            # Step 1: Flag suspicious segments
            flagged = self._flag_suspicious_segments(segments)
            logger.info(f"Flagged {len(flagged)} suspicious segments for hearing {hearing.id}")

            if not flagged:
                return StageResult(
                    success=True,
                    output={"flagged": 0, "corrected": 0},
                    cost_usd=0.0
                )

            # Limit segments to control costs
            flagged = flagged[:MAX_SEGMENTS_TO_POLISH]

            # Step 2: Get state context for better corrections
            state_code = hearing.state.code if hearing.state else ""
            state_name = hearing.state.name if hearing.state else ""

            # Step 3: Send to LLM for correction
            corrections, cost = self._get_llm_corrections(flagged, state_code, state_name)

            # Step 4: Apply corrections
            applied = 0
            for seg_id, corrected_text in corrections.items():
                segment = db.query(Segment).filter(Segment.id == seg_id).first()
                if segment and corrected_text != segment.text:
                    # Store original for reference
                    if not segment.speaker_role:
                        segment.speaker_role = f"original: {segment.text[:100]}"
                    segment.text = corrected_text
                    applied += 1

            # Update full transcript text
            if applied > 0:
                all_segments = db.query(Segment).filter(
                    Segment.hearing_id == hearing.id
                ).order_by(Segment.segment_index).all()
                transcript.full_text = " ".join(s.text for s in all_segments)

            db.commit()

            logger.info(f"LLM polish: {len(flagged)} flagged, {applied} corrected, ${cost:.4f}")

            return StageResult(
                success=True,
                output={
                    "flagged": len(flagged),
                    "corrected": applied,
                },
                cost_usd=cost
            )

        except Exception as e:
            logger.exception(f"LLM polish error for hearing {hearing.id}")
            return StageResult(
                success=False,
                error=f"LLM polish error: {str(e)}",
                should_retry=True
            )

    def _flag_suspicious_segments(self, segments: List[Segment]) -> List[FlaggedSegment]:
        """Identify segments that might have transcription errors."""
        flagged = []

        for i, seg in enumerate(segments):
            text = seg.text or ""
            reasons = []

            # Check against suspicious patterns
            for pattern, reason in SUSPICIOUS_PATTERNS:
                if re.search(pattern, text, re.IGNORECASE):
                    reasons.append(reason)

            if reasons:
                # Get surrounding context
                context_before = segments[i-1].text if i > 0 else ""
                context_after = segments[i+1].text if i < len(segments)-1 else ""

                flagged.append(FlaggedSegment(
                    segment_id=seg.id,
                    segment_index=seg.segment_index,
                    text=text,
                    reason=", ".join(reasons[:3]),
                    context_before=context_before[-100:] if context_before else "",
                    context_after=context_after[:100] if context_after else "",
                ))

        return flagged

    def _get_llm_corrections(
        self,
        flagged: List[FlaggedSegment],
        state_code: str,
        state_name: str
    ) -> Tuple[Dict[int, str], float]:
        """Send flagged segments to LLM for correction."""
        if not self.client:
            return {}, 0.0

        # Build the prompt
        segments_text = "\n".join([
            f"[{f.segment_index}] {f.text}"
            for f in flagged
        ])

        system_prompt = f"""You are correcting transcription errors in a {state_name} Public Service Commission hearing transcript.

Common errors to fix:
- "killer one/once" → "kilowatt"
- "mega hertz" → "megawatt" (in utility context)
- "air cot/er cot" → "ERCOT" (Texas)
- "see puck" → "CPUC" (California)
- "p u c o" → "PUCO" (Ohio)
- Garbled docket numbers (e.g., "five thought 973" → "55973")
- Split company names (e.g., "pg and e" → "PG&E")
- Repeated words/filler words

For each segment, output ONLY the corrected text. If no correction needed, output the original.
Output format: One corrected segment per line, numbered to match input."""

        user_prompt = f"""Correct these transcript segments:

{segments_text}

Output the corrected versions, one per line, with the same [index] prefix."""

        try:
            # Cap max_tokens to model limit (GPT-4o-mini: 16384)
            max_output_tokens = min(len(segments_text) + 500, 8000)

            response = self.client.chat.completions.create(
                model=LLM_POLISH_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=max_output_tokens,
            )

            # Parse response
            corrections = {}
            response_text = response.choices[0].message.content or ""

            for line in response_text.strip().split("\n"):
                # Match [index] text format
                match = re.match(r'\[(\d+)\]\s*(.+)', line.strip())
                if match:
                    idx = int(match.group(1))
                    corrected = match.group(2).strip()
                    # Find the segment with this index
                    for f in flagged:
                        if f.segment_index == idx:
                            corrections[f.segment_id] = corrected
                            break

            # Calculate cost
            input_tokens = response.usage.prompt_tokens if response.usage else 0
            output_tokens = response.usage.completion_tokens if response.usage else 0
            cost = (input_tokens + output_tokens) * LLM_POLISH_COST_PER_1K_TOKENS / 1000

            return corrections, cost

        except Exception as e:
            logger.error(f"LLM correction error: {e}")
            return {}, 0.0
