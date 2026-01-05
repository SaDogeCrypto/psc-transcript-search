"""
Analyze Stage - LLM analysis of transcripts.

Supports:
- Azure OpenAI (if AZURE_OPENAI_ENDPOINT is set)
- OpenAI API (if OPENAI_API_KEY is set)

Uses GPT-4o to generate comprehensive hearing analysis including:
- Executive summary
- Key takeaways
- Commissioner concerns
- Utility vulnerabilities and commitments
- Likely outcomes
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from app.pipeline.stages.base import BaseStage, StageResult
from app.models.database import Hearing, Transcript, Analysis, PipelineJob

logger = logging.getLogger(__name__)

# Azure OpenAI configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
AZURE_GPT4_DEPLOYMENT = os.getenv("AZURE_GPT4_DEPLOYMENT", "gpt-4o")

# OpenAI configuration (fallback)
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", "gpt-4o")

# Pricing (as of 2024)
GPT4O_INPUT_COST_PER_1M = 2.50
GPT4O_OUTPUT_COST_PER_1M = 10.00


ANALYSIS_SYSTEM_PROMPT = """You are a senior regulatory affairs analyst specializing in public utility commission (PSC/PUC) proceedings. Your analysis will inform executives about regulatory developments.

Your briefings are known for:
1. Cutting through procedural noise to surface strategic intelligence
2. Identifying commissioner concerns that predict decisions
3. Spotting utility vulnerabilities and commitments
4. Providing actionable insights, not just summaries

Context on PSC proceedings:
- Evidentiary hearings are formal, with sworn testimony and cross-examination
- Commissioner questions often telegraph their concerns and likely votes
- Staff recommendations are influential but not binding
- Utility commitments made on the record can be enforced in future proceedings
- Intervenors (Sierra Club, industrial customers, consumer advocates) often expose weaknesses"""

ANALYSIS_USER_PROMPT = """Analyze this PSC hearing transcript and produce a comprehensive intelligence briefing.

HEARING METADATA:
- Title: {title}
- State: {state}
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

  "participants": [
    {{"name": "Name", "role": "Role", "affiliation": "Organization"}}
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

Return ONLY valid JSON."""


class AnalyzeStage(BaseStage):
    """Analyze transcript using GPT-4o (Azure or OpenAI)."""

    name = "analyze"
    in_progress_status = "analyzing"
    complete_status = "analyzed"

    def __init__(self):
        self._openai_client = None
        self._tiktoken_encoder = None
        self._use_azure = bool(AZURE_OPENAI_ENDPOINT)

    @property
    def openai_client(self):
        """Lazy load OpenAI client (Azure or standard)."""
        if self._openai_client is None:
            if self._use_azure:
                from openai import AzureOpenAI
                self._openai_client = AzureOpenAI(
                    azure_endpoint=AZURE_OPENAI_ENDPOINT,
                    api_key=AZURE_OPENAI_API_KEY,
                    api_version=AZURE_OPENAI_API_VERSION,
                )
                logger.info(f"Using Azure OpenAI: {AZURE_OPENAI_ENDPOINT}")
            else:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                logger.info("Using OpenAI API")
        return self._openai_client

    @property
    def model_name(self):
        """Get model/deployment name."""
        return AZURE_GPT4_DEPLOYMENT if self._use_azure else ANALYSIS_MODEL

    @property
    def tiktoken_encoder(self):
        """Lazy load tiktoken encoder."""
        if self._tiktoken_encoder is None:
            import tiktoken
            self._tiktoken_encoder = tiktoken.encoding_for_model("gpt-4o")
        return self._tiktoken_encoder

    def validate(self, hearing: Hearing, db: Session) -> bool:
        """Check if transcript exists."""
        transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()

        if not transcript:
            logger.warning(f"No transcript found for hearing {hearing.id}")
            return False

        if not transcript.full_text:
            logger.warning(f"Transcript for hearing {hearing.id} has no text")
            return False

        # Check if already analyzed
        existing = db.query(Analysis).filter(Analysis.hearing_id == hearing.id).first()
        if existing:
            logger.info(f"Analysis already exists for hearing {hearing.id}")
            # Still valid - we'll skip

        return True

    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """Analyze transcript using GPT-4o."""
        # Check if already analyzed
        existing = db.query(Analysis).filter(Analysis.hearing_id == hearing.id).first()
        if existing:
            logger.info(f"Using existing analysis for hearing {hearing.id}")
            return StageResult(
                success=True,
                output={"analysis_id": existing.id, "skipped": True},
                cost_usd=0.0
            )

        # Get transcript
        transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()
        if not transcript:
            return StageResult(
                success=False,
                error="No transcript found",
                should_retry=False
            )

        # Get state info
        state = hearing.state
        state_name = state.name if state else "Unknown"

        try:
            result = self._analyze_transcript(
                hearing=hearing,
                transcript_text=transcript.full_text,
                state_name=state_name
            )

            if not result["success"]:
                return StageResult(
                    success=False,
                    error=result.get("error", "Analysis failed"),
                    should_retry=True
                )

            # Save analysis to database
            analysis = self._save_analysis(hearing, result, db)

            return StageResult(
                success=True,
                output={
                    "analysis_id": analysis.id,
                    "confidence_score": analysis.confidence_score,
                },
                cost_usd=result.get("cost_usd", 0.0)
            )

        except Exception as e:
            logger.exception(f"Analysis error for hearing {hearing.id}")
            return StageResult(
                success=False,
                error=f"Analysis error: {str(e)}",
                should_retry=True
            )

    def _analyze_transcript(self, hearing: Hearing, transcript_text: str, state_name: str) -> dict:
        """Run GPT-4o analysis on transcript."""
        logger.info(f"Analyzing hearing {hearing.id} with {self.model_name}")

        # Truncate if too long (keep ~80% of context window for safety)
        max_input_tokens = 100_000
        input_tokens = len(self.tiktoken_encoder.encode(transcript_text))

        if input_tokens > max_input_tokens:
            logger.info(f"Truncating transcript from {input_tokens} to ~{max_input_tokens} tokens")
            transcript_text = self._truncate_transcript(transcript_text, max_input_tokens)
            input_tokens = max_input_tokens

        # Build prompt
        user_prompt = ANALYSIS_USER_PROMPT.format(
            title=hearing.title,
            state=state_name,
            hearing_date=hearing.hearing_date.isoformat() if hearing.hearing_date else "Unknown",
            hearing_type=hearing.hearing_type or "Hearing",
            duration_minutes=(hearing.duration_seconds or 0) // 60,
            transcript_text=transcript_text
        )

        # Count tokens for cost
        system_tokens = len(self.tiktoken_encoder.encode(ANALYSIS_SYSTEM_PROMPT))
        prompt_tokens = system_tokens + len(self.tiktoken_encoder.encode(user_prompt))

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

            # Parse response
            content = response.choices[0].message.content
            analysis_data = json.loads(content)

            # Calculate cost
            completion_tokens = response.usage.completion_tokens
            total_prompt_tokens = response.usage.prompt_tokens
            cost_usd = (
                (total_prompt_tokens * GPT4O_INPUT_COST_PER_1M / 1_000_000) +
                (completion_tokens * GPT4O_OUTPUT_COST_PER_1M / 1_000_000)
            )

            logger.info(f"Analysis complete: {total_prompt_tokens} input, {completion_tokens} output, ${cost_usd:.4f}")

            return {
                "success": True,
                "data": analysis_data,
                "cost_usd": cost_usd,
                "model": self.model_name,
            }

        except json.JSONDecodeError as e:
            return {"success": False, "error": f"Invalid JSON response: {str(e)}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _truncate_transcript(self, text: str, max_tokens: int) -> str:
        """Truncate transcript keeping beginning and end."""
        lines = text.split('\n')
        target_lines = int(len(lines) * 0.7)
        keep_start = target_lines // 2
        keep_end = target_lines // 2
        truncated = lines[:keep_start] + ["\n[... TRANSCRIPT TRUNCATED FOR LENGTH ...]\n"] + lines[-keep_end:]
        return '\n'.join(truncated)

    def _save_analysis(self, hearing: Hearing, result: dict, db: Session) -> Analysis:
        """Save analysis to database."""
        data = result.get("data", {})

        analysis = Analysis(
            hearing_id=hearing.id,
            summary=data.get("summary"),
            one_sentence_summary=data.get("one_sentence_summary"),
            hearing_type=data.get("hearing_type"),
            utility_name=data.get("utility_name"),
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
            model=result.get("model"),
            cost_usd=result.get("cost_usd", 0.0),
            confidence_score=data.get("outcome_confidence"),
        )
        db.add(analysis)
        db.commit()

        logger.info(f"Saved analysis {analysis.id} for hearing {hearing.id}")
        return analysis

    def on_error(self, hearing: Hearing, job: PipelineJob, result: StageResult, db: Session):
        """Clean up partial analysis on error."""
        analysis = db.query(Analysis).filter(Analysis.hearing_id == hearing.id).first()
        if analysis:
            db.delete(analysis)
            db.commit()
            logger.info(f"Cleaned up partial analysis for hearing {hearing.id}")
