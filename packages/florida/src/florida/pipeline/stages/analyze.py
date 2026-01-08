"""
Florida Analyze Stage - LLM analysis of transcripts.

Adapts the core analysis logic to work with Florida models
(FLHearing, FLTranscriptSegment, FLAnalysis).

Uses GPT-4o-mini for fast, cost-effective analysis.
"""

import os
import json
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

from sqlalchemy.orm import Session

from florida.models.hearing import FLHearing, FLTranscriptSegment
from florida.models.analysis import FLAnalysis

logger = logging.getLogger(__name__)

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", "gpt-4o-mini")

# Pricing for gpt-4o-mini
GPT4O_MINI_INPUT_COST_PER_1M = 0.15
GPT4O_MINI_OUTPUT_COST_PER_1M = 0.60


ANALYSIS_SYSTEM_PROMPT = """You are a senior regulatory affairs analyst specializing in public utility commission (PSC/PUC) proceedings. Your analysis will inform executives about regulatory developments.

Your briefings are known for:
1. Cutting through procedural noise to surface strategic intelligence
2. Identifying commissioner concerns that predict decisions
3. Spotting utility vulnerabilities and commitments
4. Providing actionable insights, not just summaries

Context on Florida PSC proceedings:
- Evidentiary hearings are formal, with sworn testimony and cross-examination
- Commissioner questions often telegraph their concerns and likely votes
- Staff recommendations are influential but not binding
- Utility commitments made on the record can be enforced in future proceedings
- Intervenors (Office of Public Counsel, FIPUG, Sierra Club) often expose weaknesses"""


ANALYSIS_USER_PROMPT = """Analyze this Florida PSC hearing transcript and produce a comprehensive intelligence briefing.

HEARING METADATA:
- Title: {title}
- Docket: {docket_number}
- Date: {hearing_date}
- Type: {hearing_type}
- Duration: ~{duration_minutes} minutes

TRANSCRIPT:
---
{transcript_text}
---

Produce a JSON analysis with this structure:

{{
  "summary": "2-3 paragraph executive summary",
  "one_sentence_summary": "Single sentence capturing the key takeaway",
  "hearing_type": "Refined hearing type based on content",
  "utility_name": "Primary utility involved",
  "sector": "One of: electric, gas, water, telecom, multi",

  "participants": [
    {{"name": "Name", "role": "Role", "affiliation": "Organization"}}
  ],

  "topics": [
    {{
      "name": "Topic name",
      "relevance": "high, medium, or low",
      "sentiment": "positive, negative, neutral, or mixed",
      "context": "One sentence describing how this topic was discussed"
    }}
  ],

  "utilities": [
    {{
      "name": "Full company name",
      "aliases": ["Any abbreviations or alternate names used"],
      "role": "applicant, intervenor, or subject",
      "context": "Brief description of their involvement"
    }}
  ],

  "issues": [
    {{"issue": "Key issue", "description": "Brief description"}}
  ],

  "commitments": [
    {{"commitment": "What was committed", "by_whom": "Who made it", "context": "Context"}}
  ],

  "vulnerabilities": [
    "Weakness or vulnerability exposed"
  ],

  "commissioner_concerns": [
    {{"commissioner": "Name", "concern": "What they're worried about"}}
  ],

  "commissioner_mood": "One of: supportive, skeptical, hostile, neutral, mixed",

  "public_comments": "Summary of public input if any",
  "public_sentiment": "One of: supportive, opposed, mixed, none",

  "likely_outcome": "Predicted outcome and reasoning",
  "outcome_confidence": 0.0-1.0,

  "risk_factors": [
    "Risk or uncertainty"
  ],

  "action_items": [
    "Follow-up action needed"
  ],

  "quotes": [
    {{"speaker": "Name", "quote": "Notable quote", "significance": "Why it matters"}}
  ]
}}

STANDARD TOPIC NAMES (use these when applicable):
- Policy: grid reliability, renewable energy, rate design, energy efficiency, demand response, net metering, carbon reduction, electrification
- Technical: solar interconnection, battery storage, grid modernization, smart meters, EV charging, transmission planning, cybersecurity
- Regulatory: rate case, integrated resource plan, certificate of need, fuel cost recovery, storm cost recovery, affiliate transactions
- Consumer: low income programs, bill assistance, disconnection policy, consumer complaints

Return ONLY valid JSON."""


@dataclass
class AnalysisResult:
    """Result of analysis."""
    success: bool
    data: Dict[str, Any] = None
    model: str = ""
    cost_usd: float = 0.0
    error: str = ""

    def __post_init__(self):
        if self.data is None:
            self.data = {}


class FLAnalyzeStage:
    """
    Analyze Florida hearing transcripts using GPT-4o-mini.

    Adapts the main app's AnalyzeStage logic to work with
    Florida's FLHearing, FLTranscriptSegment, and FLAnalysis models.
    """

    name = "analyze"

    def __init__(self):
        self._openai_client = None
        self._tiktoken_encoder = None

    @property
    def openai_client(self):
        """Lazy load OpenAI client."""
        if self._openai_client is None:
            from openai import OpenAI
            self._openai_client = OpenAI(api_key=OPENAI_API_KEY)
            logger.info(f"Using OpenAI API with model {ANALYSIS_MODEL}")
        return self._openai_client

    @property
    def model_name(self):
        return ANALYSIS_MODEL

    @property
    def tiktoken_encoder(self):
        """Lazy load tiktoken encoder."""
        if self._tiktoken_encoder is None:
            import tiktoken
            self._tiktoken_encoder = tiktoken.encoding_for_model("gpt-4o")
        return self._tiktoken_encoder

    def validate(self, hearing: FLHearing, db: Session) -> tuple[bool, str]:
        """Check if hearing can be analyzed."""
        # Check for existing analysis
        existing = db.query(FLAnalysis).filter(FLAnalysis.hearing_id == hearing.id).first()
        if existing:
            return False, "Already analyzed"

        # Check for transcript content
        if hearing.full_text:
            if len(hearing.full_text.strip()) < 100:
                return False, "Transcript too short"
            return True, ""

        # Check for segments
        segment_count = db.query(FLTranscriptSegment).filter(
            FLTranscriptSegment.hearing_id == hearing.id
        ).count()

        if segment_count == 0:
            return False, "No transcript found"

        return True, ""

    def execute(self, hearing: FLHearing, db: Session) -> AnalysisResult:
        """Analyze transcript for a Florida hearing."""
        # Check for existing analysis
        existing = db.query(FLAnalysis).filter(FLAnalysis.hearing_id == hearing.id).first()
        if existing:
            return AnalysisResult(
                success=True,
                data={"analysis_id": existing.id, "skipped": True},
                error="Already analyzed (skipped)"
            )

        # Get transcript text
        transcript_text = self._get_transcript_text(hearing, db)
        if not transcript_text or len(transcript_text.strip()) < 100:
            return AnalysisResult(
                success=False,
                error="No transcript text found or transcript too short"
            )

        try:
            result = self._analyze_transcript(hearing, transcript_text)

            if not result.success:
                return result

            # Save analysis to database
            analysis = self._save_analysis(hearing, result, db)

            return AnalysisResult(
                success=True,
                data={
                    "analysis_id": analysis.id,
                    "confidence_score": analysis.confidence_score,
                    **result.data
                },
                model=result.model,
                cost_usd=result.cost_usd,
            )

        except Exception as e:
            logger.exception(f"Analysis error for hearing {hearing.id}")
            return AnalysisResult(
                success=False,
                error=f"Analysis error: {str(e)}"
            )

    def _get_transcript_text(self, hearing: FLHearing, db: Session) -> str:
        """Get transcript text from hearing or segments."""
        # Prefer full_text if available
        if hearing.full_text and len(hearing.full_text.strip()) >= 100:
            return hearing.full_text

        # Build from segments
        segments = db.query(FLTranscriptSegment).filter(
            FLTranscriptSegment.hearing_id == hearing.id
        ).order_by(FLTranscriptSegment.segment_index).all()

        if not segments:
            return ""

        text_parts = []
        for seg in segments:
            if seg.speaker_name or seg.speaker_label:
                speaker = seg.speaker_name or seg.speaker_label
                text_parts.append(f"{speaker}: {seg.text}")
            else:
                text_parts.append(seg.text)

        return "\n".join(text_parts)

    def _analyze_transcript(self, hearing: FLHearing, transcript_text: str) -> AnalysisResult:
        """Run GPT-4o analysis on transcript."""
        logger.info(f"Analyzing hearing {hearing.id} with {self.model_name}")

        # Truncate if too long
        max_input_tokens = 100_000
        input_tokens = len(self.tiktoken_encoder.encode(transcript_text))

        if input_tokens > max_input_tokens:
            logger.info(f"Truncating transcript from {input_tokens} to ~{max_input_tokens} tokens")
            transcript_text = self._truncate_transcript(transcript_text, max_input_tokens)

        # Build prompt
        user_prompt = ANALYSIS_USER_PROMPT.format(
            title=hearing.title or "Unknown",
            docket_number=hearing.docket_number or "Unknown",
            hearing_date=hearing.hearing_date.isoformat() if hearing.hearing_date else "Unknown",
            hearing_type=hearing.hearing_type or "Hearing",
            duration_minutes=(hearing.duration_seconds or 0) // 60,
            transcript_text=transcript_text
        )

        # Retry with exponential backoff for rate limits
        max_retries = 5
        base_delay = 60

        for attempt in range(max_retries):
            try:
                response = self.openai_client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.2,
                    response_format={"type": "json_object"},
                    max_tokens=4000
                )
                break
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate limit" in error_str.lower():
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"Rate limited on attempt {attempt + 1}, waiting {delay}s...")
                        time.sleep(delay)
                        continue
                raise

        # Parse response
        try:
            content = response.choices[0].message.content
            analysis_data = json.loads(content)

            # Calculate cost
            completion_tokens = response.usage.completion_tokens
            total_prompt_tokens = response.usage.prompt_tokens
            cost_usd = (
                (total_prompt_tokens * GPT4O_MINI_INPUT_COST_PER_1M / 1_000_000) +
                (completion_tokens * GPT4O_MINI_OUTPUT_COST_PER_1M / 1_000_000)
            )

            logger.info(f"Analysis complete: {total_prompt_tokens} input, {completion_tokens} output, ${cost_usd:.4f}")

            return AnalysisResult(
                success=True,
                data=analysis_data,
                model=self.model_name,
                cost_usd=cost_usd,
            )

        except json.JSONDecodeError as e:
            return AnalysisResult(success=False, error=f"Invalid JSON response: {str(e)}")
        except Exception as e:
            return AnalysisResult(success=False, error=str(e))

    def _truncate_transcript(self, text: str, max_tokens: int) -> str:
        """Truncate transcript keeping beginning and end."""
        lines = text.split('\n')
        target_lines = int(len(lines) * 0.7)
        keep_start = target_lines // 2
        keep_end = target_lines // 2
        truncated = lines[:keep_start] + ["\n[... TRANSCRIPT TRUNCATED FOR LENGTH ...]\n"] + lines[-keep_end:]
        return '\n'.join(truncated)

    def _save_analysis(self, hearing: FLHearing, result: AnalysisResult, db: Session) -> FLAnalysis:
        """Save analysis to FLAnalysis."""
        data = result.data

        analysis = FLAnalysis(
            hearing_id=hearing.id,
            summary=data.get("summary"),
            one_sentence_summary=data.get("one_sentence_summary"),
            hearing_type=data.get("hearing_type"),
            utility_name=data.get("utility_name"),
            sector=data.get("sector"),
            participants_json=data.get("participants"),
            issues_json=data.get("issues"),
            commitments_json=data.get("commitments"),
            vulnerabilities_json=data.get("vulnerabilities"),
            commissioner_concerns_json=data.get("commissioner_concerns"),
            commissioner_mood=data.get("commissioner_mood"),
            public_comments=data.get("public_comments"),
            public_sentiment=data.get("public_sentiment"),
            likely_outcome=data.get("likely_outcome"),
            outcome_confidence=data.get("outcome_confidence"),
            risk_factors_json=data.get("risk_factors"),
            action_items_json=data.get("action_items"),
            quotes_json=data.get("quotes"),
            topics_extracted=data.get("topics"),
            utilities_extracted=data.get("utilities"),
            dockets_extracted=data.get("dockets"),
            model=result.model,
            cost_usd=result.cost_usd,
            confidence_score=data.get("outcome_confidence"),
        )
        db.add(analysis)

        # Update hearing status
        hearing.transcript_status = "analyzed"

        db.commit()
        logger.info(f"Saved analysis {analysis.id} for hearing {hearing.id}")

        return analysis


__all__ = ['FLAnalyzeStage', 'AnalysisResult']
