"""
Analyze stage - LLM analysis of hearing transcripts.

Uses GPT-4o-mini for fast, cost-effective analysis.
Extracts structured intelligence:
- Executive summary
- Participants
- Issues and topics
- Commissioner sentiment
- Outcome predictions
- Action items
"""

import json
import logging
import time
from datetime import datetime
from typing import Tuple, Optional, Dict, Any

from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.models.hearing import Hearing
from src.core.models.transcript import TranscriptSegment
from src.core.models.analysis import Analysis
from src.core.pipeline.base import PipelineStage, StageResult

logger = logging.getLogger(__name__)
settings = get_settings()

# Pricing for GPT-4o-mini
GPT4O_MINI_INPUT_COST_PER_1M = 0.15
GPT4O_MINI_OUTPUT_COST_PER_1M = 0.60

# State-specific system prompt context
STATE_CONTEXT = {
    "FL": """Context on Florida PSC proceedings:
- Evidentiary hearings are formal, with sworn testimony and cross-examination
- Commissioner questions often telegraph their concerns and likely votes
- Staff recommendations are influential but not binding
- Utility commitments made on the record can be enforced in future proceedings
- Intervenors (Office of Public Counsel, FIPUG, Sierra Club) often expose weaknesses
- Docket format: YYYYNNNN-XX (e.g., 20240001-EI for electric)""",

    "TX": """Context on Texas PUC proceedings:
- ERCOT manages the Texas grid independently from federal regulation
- Rate cases use a "file and suspend" process
- Public participation is encouraged through public comment periods
- Commissioners are appointed by the Governor
- Docket format: 5-digit control numbers""",

    "CA": """Context on California PUC proceedings:
- Formal proceedings include applications (A.) and rulemakings (R.)
- Administrative Law Judges (ALJs) issue proposed decisions
- Commissioners vote on final decisions at public meetings
- Intervenor compensation is available for public participation
- Strong focus on climate and environmental policy""",
}


SYSTEM_PROMPT_TEMPLATE = """You are a senior regulatory affairs analyst specializing in public utility commission (PSC/PUC) proceedings. Your analysis will inform executives about regulatory developments.

Your briefings are known for:
1. Cutting through procedural noise to surface strategic intelligence
2. Identifying commissioner concerns that predict decisions
3. Spotting utility vulnerabilities and commitments
4. Providing actionable insights, not just summaries

{state_context}"""


USER_PROMPT_TEMPLATE = """Analyze this {state_name} hearing transcript and produce a comprehensive intelligence briefing.

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


STATE_NAMES = {
    "FL": "Florida PSC",
    "TX": "Texas PUC",
    "CA": "California PUC",
    "GA": "Georgia PSC",
    "NY": "New York PSC",
}


class AnalyzeStage(PipelineStage[Hearing]):
    """
    Analyze hearing transcripts using GPT-4o-mini.

    Extracts structured intelligence including participants,
    issues, sentiment, and predictions.
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
            self._openai_client = OpenAI(api_key=settings.openai_api_key)
            logger.info(f"Using OpenAI API with model {settings.analysis_model}")
        return self._openai_client

    @property
    def tiktoken_encoder(self):
        """Lazy load tiktoken encoder."""
        if self._tiktoken_encoder is None:
            import tiktoken
            self._tiktoken_encoder = tiktoken.encoding_for_model("gpt-4o")
        return self._tiktoken_encoder

    def validate(self, hearing: Hearing, db: Session) -> Tuple[bool, str]:
        """Check if hearing can be analyzed."""
        if not settings.openai_api_key:
            return False, "No OpenAI API key configured"

        # Check for existing analysis
        existing = db.query(Analysis).filter(Analysis.hearing_id == hearing.id).first()
        if existing:
            return False, "Already analyzed"

        # Check for transcript content
        if hearing.full_text:
            if len(hearing.full_text.strip()) < 100:
                return False, "Transcript too short"
            return True, ""

        # Check for segments
        segment_count = db.query(TranscriptSegment).filter(
            TranscriptSegment.hearing_id == hearing.id
        ).count()

        if segment_count == 0:
            return False, "No transcript found"

        return True, ""

    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """Analyze transcript and save results."""
        # Check for existing analysis
        existing = db.query(Analysis).filter(Analysis.hearing_id == hearing.id).first()
        if existing:
            return StageResult(
                success=True,
                skipped=True,
                data={"analysis_id": str(existing.id)},
                error="Already analyzed"
            )

        # Get transcript text
        transcript_text = self._get_transcript_text(hearing, db)
        if not transcript_text or len(transcript_text.strip()) < 100:
            return StageResult(
                success=False,
                error="No transcript text found or transcript too short"
            )

        try:
            # Run analysis
            analysis_data, cost = self._analyze_transcript(hearing, transcript_text)

            # Save to database
            analysis = self._save_analysis(hearing, analysis_data, cost, db)

            return StageResult(
                success=True,
                data={
                    "analysis_id": str(analysis.id),
                    "confidence_score": analysis.confidence_score,
                    "utility": analysis.utility_name,
                    "sector": analysis.sector,
                },
                cost_usd=cost,
                model=settings.analysis_model,
            )

        except Exception as e:
            logger.exception(f"Analysis error for hearing {hearing.id}")
            return StageResult(success=False, error=str(e))

    def _get_transcript_text(self, hearing: Hearing, db: Session) -> str:
        """Get transcript text from hearing or segments."""
        # Prefer full_text if available
        if hearing.full_text and len(hearing.full_text.strip()) >= 100:
            return hearing.full_text

        # Build from segments
        segments = db.query(TranscriptSegment).filter(
            TranscriptSegment.hearing_id == hearing.id
        ).order_by(TranscriptSegment.segment_index).all()

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

    def _analyze_transcript(self, hearing: Hearing, transcript_text: str) -> Tuple[Dict, float]:
        """Run GPT-4o-mini analysis on transcript."""
        logger.info(f"Analyzing hearing {hearing.id} with {settings.analysis_model}")

        # Truncate if too long
        max_input_tokens = 100_000
        input_tokens = len(self.tiktoken_encoder.encode(transcript_text))

        if input_tokens > max_input_tokens:
            logger.info(f"Truncating transcript from {input_tokens} to ~{max_input_tokens} tokens")
            transcript_text = self._truncate_transcript(transcript_text, max_input_tokens)

        # Build prompts
        state_context = STATE_CONTEXT.get(hearing.state_code, "")
        state_name = STATE_NAMES.get(hearing.state_code, "Public Utility Commission")

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(state_context=state_context)
        user_prompt = USER_PROMPT_TEMPLATE.format(
            state_name=state_name,
            title=hearing.title or "Unknown",
            docket_number=hearing.docket_number or "Unknown",
            hearing_date=hearing.hearing_date.isoformat() if hearing.hearing_date else "Unknown",
            hearing_type=hearing.hearing_type or "Hearing",
            duration_minutes=hearing.duration_minutes or 0,
            transcript_text=transcript_text
        )

        # Retry with exponential backoff for rate limits
        max_retries = 5
        base_delay = 60

        for attempt in range(max_retries):
            try:
                response = self.openai_client.chat.completions.create(
                    model=settings.analysis_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
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

        return analysis_data, cost_usd

    def _truncate_transcript(self, text: str, max_tokens: int) -> str:
        """Truncate transcript keeping beginning and end."""
        lines = text.split('\n')
        target_lines = int(len(lines) * 0.7)
        keep_start = target_lines // 2
        keep_end = target_lines // 2
        truncated = lines[:keep_start] + ["\n[... TRANSCRIPT TRUNCATED FOR LENGTH ...]\n"] + lines[-keep_end:]
        return '\n'.join(truncated)

    def _save_analysis(
        self,
        hearing: Hearing,
        data: Dict[str, Any],
        cost: float,
        db: Session
    ) -> Analysis:
        """Save analysis to database."""
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
            model=settings.analysis_model,
            cost_usd=cost,
            confidence_score=data.get("outcome_confidence"),
        )
        db.add(analysis)

        # Update hearing status
        hearing.transcript_status = "analyzed"
        hearing.processing_cost_usd = (hearing.processing_cost_usd or 0) + cost

        db.commit()
        logger.info(f"Saved analysis {analysis.id} for hearing {hearing.id}")

        return analysis
