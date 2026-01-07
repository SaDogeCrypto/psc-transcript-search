"""
Analyze Stage - LLM analysis of transcripts + entity linking.

Uses OpenAI API with GPT-4o-mini for fast, cost-effective analysis.

Generates comprehensive hearing analysis including:
- Executive summary
- Key takeaways
- Commissioner concerns
- Utility vulnerabilities and commitments
- Likely outcomes

Then links extracted entities (topics, utilities, dockets) to normalized tables.
"""

import os
from dotenv import load_dotenv
load_dotenv()  # Load .env before reading environment variables

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple, List

from sqlalchemy.orm import Session

from app.pipeline.stages.base import BaseStage, StageResult
from app.models.database import (
    Hearing, Transcript, Analysis, PipelineJob,
    Topic, Utility, Docket, KnownDocket, State,
    HearingTopic, HearingUtility, HearingDocket
)
from app.services.docket_parser import parse_docket, normalize_for_matching
from app.pipeline.entity_validation import (
    EntityValidationPipeline,
    ValidatedTopic, ValidatedUtility, ValidatedDocket
)

logger = logging.getLogger(__name__)

# OpenAI configuration - use gpt-4o-mini for speed and cost
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", "gpt-4o-mini")

# Pricing for gpt-4o-mini (as of 2024)
GPT4O_MINI_INPUT_COST_PER_1M = 0.15
GPT4O_MINI_OUTPUT_COST_PER_1M = 0.60

# Try to import optional dependencies for entity linking
try:
    from rapidfuzz import fuzz, process
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    logger.warning("rapidfuzz not installed - fuzzy matching disabled")

try:
    from slugify import slugify
    SLUGIFY_AVAILABLE = True
except ImportError:
    SLUGIFY_AVAILABLE = False
    # Fallback slugify implementation
    def slugify(text: str) -> str:
        """Simple slugify fallback."""
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text)
        return text


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
  "sector": "One of: electric, gas, water, telecom, multi",

  "participants": [
    {{"name": "Name", "role": "Role", "affiliation": "Organization"}}
  ],

  "topics": [
    {{
      "name": "Topic name - use standard names from the list below when matching",
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


class AnalyzeStage(BaseStage):
    """Analyze transcript using OpenAI GPT-4o-mini and link extracted entities."""

    name = "analyze"
    in_progress_status = "analyzing"
    complete_status = "analyzed"

    def __init__(self):
        self._openai_client = None
        self._tiktoken_encoder = None
        self._topic_cache: Optional[Dict[str, Topic]] = None
        self._utility_cache: Optional[Dict[str, Utility]] = None
        self._known_dockets_cache: Dict[str, Dict[str, KnownDocket]] = {}

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
        """Get model name."""
        return ANALYSIS_MODEL

    @property
    def tiktoken_encoder(self):
        """Lazy load tiktoken encoder."""
        if self._tiktoken_encoder is None:
            import tiktoken
            # Use gpt-4o encoding (compatible with gpt-4o-mini)
            self._tiktoken_encoder = tiktoken.encoding_for_model("gpt-4o")
        return self._tiktoken_encoder

    def validate(self, hearing: Hearing, db: Session) -> bool:
        """Check if transcript exists and has content."""
        transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing.id).first()

        if not transcript:
            logger.warning(f"No transcript found for hearing {hearing.id}")
            return False

        if not transcript.full_text:
            logger.warning(f"Transcript for hearing {hearing.id} has no text")
            return False

        # Check that transcript has meaningful content (not empty or very short)
        text_length = len(transcript.full_text.strip())
        if text_length < 100:
            logger.warning(f"Transcript for hearing {hearing.id} is too short ({text_length} chars)")
            return False

        # Check if already analyzed
        existing = db.query(Analysis).filter(Analysis.hearing_id == hearing.id).first()
        if existing:
            logger.info(f"Analysis already exists for hearing {hearing.id}")
            # Still valid - we'll skip

        return True

    def execute(self, hearing: Hearing, db: Session) -> StageResult:
        """Analyze transcript using GPT-4o and link entities."""
        # Check if already analyzed
        existing = db.query(Analysis).filter(Analysis.hearing_id == hearing.id).first()
        if existing:
            logger.info(f"Using existing analysis for hearing {hearing.id}")
            # Still run entity linking in case it was interrupted
            link_stats = self._link_entities(hearing, existing, db)
            return StageResult(
                success=True,
                output={"analysis_id": existing.id, "skipped": True, **link_stats},
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

            # Link extracted entities (topics, utilities, dockets)
            link_stats = self._link_entities(hearing, analysis, db)

            return StageResult(
                success=True,
                output={
                    "analysis_id": analysis.id,
                    "confidence_score": analysis.confidence_score,
                    **link_stats
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

        # Retry with exponential backoff for rate limits
        max_retries = 5
        base_delay = 60  # Start with 60 seconds for Azure rate limits

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
                break  # Success, exit retry loop
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RateLimitReached" in error_str or "rate limit" in error_str.lower():
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)  # Exponential backoff: 60, 120, 240, 480 seconds
                        logger.warning(f"Rate limited on attempt {attempt + 1}, waiting {delay}s before retry...")
                        time.sleep(delay)
                        continue
                raise  # Re-raise if not a rate limit error or max retries exceeded

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
            # Entity extraction results
            topics_extracted=data.get("topics"),
            utilities_extracted=data.get("utilities"),
            dockets_extracted=data.get("dockets"),
            model=result.get("model"),
            cost_usd=result.get("cost_usd", 0.0),
            confidence_score=data.get("outcome_confidence"),
        )
        db.add(analysis)
        db.commit()

        logger.info(f"Saved analysis {analysis.id} for hearing {hearing.id}")
        return analysis

    # ==================== Entity Linking Methods ====================

    def _link_entities(self, hearing: Hearing, analysis: Analysis, db: Session) -> dict:
        """Link extracted topics and utilities for a hearing with smart validation.

        Note: Docket extraction is handled separately by the SmartExtract stage
        using regex patterns against known dockets for higher accuracy.
        """
        # Clean up previous topic and utility links (for re-processing)
        # Note: We don't touch dockets - those are managed by SmartExtract stage
        db.query(HearingTopic).filter(HearingTopic.hearing_id == hearing.id).delete()
        db.query(HearingUtility).filter(HearingUtility.hearing_id == hearing.id).delete()

        stats = {
            'topics_linked': 0,
            'topics_created': 0,
            'utilities_linked': 0,
            'utilities_created': 0,
            'needs_review': 0,
        }

        # Build hearing context for validation
        hearing_context = {
            'title': hearing.title or '',
            'summary': analysis.summary or '',
            'state_code': hearing.state.code if hearing.state else 'XX',
            'hearing_date': hearing.hearing_date.isoformat() if hearing.hearing_date else '',
        }

        # Validate topics and utilities through unified pipeline
        # Note: Pass empty list for dockets - SmartExtract stage handles those
        validation_pipeline = EntityValidationPipeline(db)
        validated = validation_pipeline.validate_all(
            topics_extracted=analysis.topics_extracted or [],
            utilities_extracted=analysis.utilities_extracted or [],
            dockets_extracted=[],  # Dockets handled by SmartExtract stage
            hearing_context=hearing_context
        )

        # Link topics with validation results
        for validated_topic in validated['topics']:
            topic, created = self._link_topic_validated(validated_topic, db)
            if topic:
                self._create_hearing_topic_validated(hearing, topic, validated_topic, db)
                stats['topics_linked'] += 1
                if created:
                    stats['topics_created'] += 1
                if validated_topic.status == 'needs_review':
                    stats['needs_review'] += 1

        # Link utilities with validation results
        for validated_utility in validated['utilities']:
            utility, created = self._link_utility_validated(validated_utility, db)
            if utility:
                self._create_hearing_utility_validated(hearing, utility, validated_utility, db)
                stats['utilities_linked'] += 1
                if created:
                    stats['utilities_created'] += 1
                if validated_utility.status == 'needs_review':
                    stats['needs_review'] += 1

                # Set primary utility if applicant
                if validated_utility.role == 'applicant' and not hearing.primary_utility_id:
                    hearing.primary_utility_id = utility.id

        # Update hearing metadata (sector from analysis, dockets from SmartExtract)
        hearing.sector = analysis.sector

        db.commit()

        logger.info(
            f"Linked hearing {hearing.id}: "
            f"{stats['topics_linked']} topics ({stats['topics_created']} new), "
            f"{stats['utilities_linked']} utilities ({stats['utilities_created']} new), "
            f"{stats['needs_review']} need review"
        )

        return stats

    def _cleanup_previous_links(self, hearing: Hearing, db: Session):
        """Remove previous links for re-processing."""
        deleted_topics = db.query(HearingTopic).filter(
            HearingTopic.hearing_id == hearing.id
        ).delete()

        deleted_utilities = db.query(HearingUtility).filter(
            HearingUtility.hearing_id == hearing.id
        ).delete()

        deleted_dockets = db.query(HearingDocket).filter(
            HearingDocket.hearing_id == hearing.id
        ).delete()

        if deleted_topics or deleted_utilities or deleted_dockets:
            logger.info(
                f"Cleaned up previous links for hearing {hearing.id}: "
                f"{deleted_topics} topics, {deleted_utilities} utilities, {deleted_dockets} dockets"
            )

    def _load_topic_cache(self, db: Session) -> Dict[str, Topic]:
        """Load all topics into cache for matching."""
        if self._topic_cache is None:
            topics = db.query(Topic).all()
            self._topic_cache = {}
            for t in topics:
                self._topic_cache[t.slug] = t
                self._topic_cache[t.name.lower()] = t
        return self._topic_cache

    def _load_utility_cache(self, db: Session) -> Dict[str, Utility]:
        """Load all utilities into cache for matching."""
        if self._utility_cache is None:
            utilities = db.query(Utility).all()
            self._utility_cache = {}
            for u in utilities:
                self._utility_cache[u.normalized_name] = u
                self._utility_cache[u.name.lower()] = u
                for alias in (u.aliases or []):
                    self._utility_cache[alias.lower()] = u
        return self._utility_cache

    def _link_topic(self, topic_data: Dict[str, Any], db: Session) -> Tuple[Optional[Topic], bool]:
        """Link extracted topic to topics table. Returns (topic, was_created)."""
        name = topic_data.get('name', '').strip()
        if not name:
            return None, False

        cache = self._load_topic_cache(db)
        slug = slugify(name)

        # Exact match by slug
        if slug in cache:
            topic = cache[slug]
            topic.mention_count = (topic.mention_count or 0) + 1
            return topic, False

        # Exact match by name
        if name.lower() in cache:
            topic = cache[name.lower()]
            topic.mention_count = (topic.mention_count or 0) + 1
            return topic, False

        # Fuzzy match if available
        if FUZZY_AVAILABLE:
            all_names = [t.name for t in db.query(Topic).all()]
            if all_names:
                match = process.extractOne(name, all_names, score_cutoff=85)
                if match:
                    topic = db.query(Topic).filter(Topic.name == match[0]).first()
                    if topic:
                        topic.mention_count = (topic.mention_count or 0) + 1
                        return topic, False

        # Create new topic (needs review)
        new_topic = Topic(
            name=name,
            slug=slug,
            category='uncategorized',
            mention_count=1,
        )
        db.add(new_topic)
        db.flush()

        # Add to cache
        self._topic_cache[slug] = new_topic
        self._topic_cache[name.lower()] = new_topic

        logger.info(f"Created new topic: {name}")
        return new_topic, True

    def _create_hearing_topic(self, hearing: Hearing, topic: Topic, topic_data: Dict[str, Any], db: Session):
        """Create hearing_topics junction record."""
        existing = db.query(HearingTopic).filter(
            HearingTopic.hearing_id == hearing.id,
            HearingTopic.topic_id == topic.id
        ).first()

        if existing:
            return

        relevance_map = {'high': 0.9, 'medium': 0.6, 'low': 0.3}

        ht = HearingTopic(
            hearing_id=hearing.id,
            topic_id=topic.id,
            relevance_score=relevance_map.get(topic_data.get('relevance', 'medium'), 0.5),
            sentiment=topic_data.get('sentiment'),
            context_summary=topic_data.get('context'),
            confidence='auto',
            needs_review=True,  # All topics require manual review
        )
        db.add(ht)

    def _link_utility(self, utility_data: Dict[str, Any], db: Session) -> Tuple[Optional[Utility], bool]:
        """Link extracted utility to utilities table. Returns (utility, was_created)."""
        name = utility_data.get('name', '').strip()
        if not name:
            return None, False

        normalized = slugify(name)
        aliases = utility_data.get('aliases', [])

        cache = self._load_utility_cache(db)

        # Check cache first
        if normalized in cache:
            utility = cache[normalized]
            utility.mention_count = (utility.mention_count or 0) + 1
            self._update_utility_aliases(utility, aliases)
            return utility, False

        if name.lower() in cache:
            utility = cache[name.lower()]
            utility.mention_count = (utility.mention_count or 0) + 1
            self._update_utility_aliases(utility, aliases)
            return utility, False

        # Check aliases
        for alias in aliases:
            if alias.lower() in cache:
                utility = cache[alias.lower()]
                utility.mention_count = (utility.mention_count or 0) + 1
                self._update_utility_aliases(utility, aliases)
                return utility, False

        # Fuzzy match if available
        if FUZZY_AVAILABLE:
            all_utilities = db.query(Utility).all()
            all_names = [u.name for u in all_utilities]
            if all_names:
                match = process.extractOne(name, all_names, score_cutoff=85)
                if match:
                    utility = next(u for u in all_utilities if u.name == match[0])
                    utility.mention_count = (utility.mention_count or 0) + 1
                    self._update_utility_aliases(utility, aliases)
                    return utility, False

        # Create new utility
        new_utility = Utility(
            name=name,
            normalized_name=normalized,
            aliases=aliases if aliases else [],
            mention_count=1,
        )
        db.add(new_utility)
        db.flush()

        # Add to cache
        self._utility_cache[normalized] = new_utility
        self._utility_cache[name.lower()] = new_utility
        for alias in aliases:
            self._utility_cache[alias.lower()] = new_utility

        logger.info(f"Created new utility: {name}")
        return new_utility, True

    def _update_utility_aliases(self, utility: Utility, new_aliases: List[str]):
        """Update utility with new aliases."""
        current_aliases = utility.aliases or []
        changed = False
        for alias in new_aliases:
            if alias not in current_aliases and alias != utility.name:
                current_aliases.append(alias)
                changed = True
        if changed:
            utility.aliases = current_aliases

    def _create_hearing_utility(self, hearing: Hearing, utility: Utility, utility_data: Dict[str, Any], db: Session):
        """Create hearing_utilities junction record."""
        existing = db.query(HearingUtility).filter(
            HearingUtility.hearing_id == hearing.id,
            HearingUtility.utility_id == utility.id
        ).first()

        if existing:
            return

        hu = HearingUtility(
            hearing_id=hearing.id,
            utility_id=utility.id,
            role=utility_data.get('role'),
            context_summary=utility_data.get('context'),
            confidence='auto',
        )
        db.add(hu)

    # ==================== Validated Entity Linking Methods ====================

    def _link_topic_validated(self, validated: ValidatedTopic, db: Session) -> Tuple[Optional[Topic], bool]:
        """Link validated topic to topics table. Returns (topic, was_created)."""
        if not validated.raw_name:
            return None, False

        cache = self._load_topic_cache(db)

        # If matched to existing topic, use it
        if validated.matched_id:
            topic = db.query(Topic).get(validated.matched_id)
            if topic:
                topic.mention_count = (topic.mention_count or 0) + 1
                return topic, False

        # Check cache by slug
        if validated.normalized_name in cache:
            topic = cache[validated.normalized_name]
            topic.mention_count = (topic.mention_count or 0) + 1
            return topic, False

        # Create new topic
        new_topic = Topic(
            name=validated.raw_name,
            slug=validated.normalized_name,
            category=validated.suggested_category or 'uncategorized',
            mention_count=1,
        )
        db.add(new_topic)
        db.flush()

        # Add to cache
        self._topic_cache[validated.normalized_name] = new_topic
        self._topic_cache[validated.raw_name.lower()] = new_topic

        logger.info(f"Created new topic: {validated.raw_name} (confidence={validated.confidence})")
        return new_topic, True

    def _create_hearing_topic_validated(self, hearing: Hearing, topic: Topic, validated: ValidatedTopic, db: Session):
        """Create hearing_topics junction record with validation data."""
        existing = db.query(HearingTopic).filter(
            HearingTopic.hearing_id == hearing.id,
            HearingTopic.topic_id == topic.id
        ).first()

        if existing:
            # Update with validation data
            existing.confidence_score = validated.confidence
            existing.match_type = validated.match_type
            existing.needs_review = True  # All topics require manual review
            return

        relevance_map = {'high': 0.9, 'medium': 0.6, 'low': 0.3}

        ht = HearingTopic(
            hearing_id=hearing.id,
            topic_id=topic.id,
            relevance_score=relevance_map.get(validated.relevance, 0.5),
            sentiment=validated.sentiment,
            context_summary=validated.context,
            confidence=validated.match_type,  # exact, fuzzy, none
            confidence_score=validated.confidence,
            match_type=validated.match_type,
            needs_review=True,  # All topics require manual review
            review_reason=validated.review_reason,
        )
        db.add(ht)

    def _link_utility_validated(self, validated: ValidatedUtility, db: Session) -> Tuple[Optional[Utility], bool]:
        """Link validated utility to utilities table. Returns (utility, was_created)."""
        if not validated.raw_name:
            return None, False

        cache = self._load_utility_cache(db)

        # If matched to existing utility, use it
        if validated.matched_id:
            utility = db.query(Utility).get(validated.matched_id)
            if utility:
                utility.mention_count = (utility.mention_count or 0) + 1
                self._update_utility_aliases(utility, validated.aliases)
                return utility, False

        # Check cache
        if validated.normalized_name in cache:
            utility = cache[validated.normalized_name]
            utility.mention_count = (utility.mention_count or 0) + 1
            self._update_utility_aliases(utility, validated.aliases)
            return utility, False

        # Create new utility
        new_utility = Utility(
            name=validated.raw_name,
            normalized_name=validated.normalized_name,
            aliases=validated.aliases if validated.aliases else [],
            utility_type=validated.utility_type,
            mention_count=1,
        )
        db.add(new_utility)
        db.flush()

        # Add to cache
        self._utility_cache[validated.normalized_name] = new_utility
        self._utility_cache[validated.raw_name.lower()] = new_utility
        for alias in validated.aliases:
            self._utility_cache[alias.lower()] = new_utility

        logger.info(f"Created new utility: {validated.raw_name} (confidence={validated.confidence})")
        return new_utility, True

    def _create_hearing_utility_validated(self, hearing: Hearing, utility: Utility, validated: ValidatedUtility, db: Session):
        """Create hearing_utilities junction record with validation data."""
        existing = db.query(HearingUtility).filter(
            HearingUtility.hearing_id == hearing.id,
            HearingUtility.utility_id == utility.id
        ).first()

        if existing:
            # Update with validation data
            existing.confidence_score = validated.confidence
            existing.match_type = validated.match_type
            existing.needs_review = True  # All utilities require manual review
            return

        hu = HearingUtility(
            hearing_id=hearing.id,
            utility_id=utility.id,
            role=validated.role,
            context_summary=validated.context,
            confidence=validated.match_type,
            confidence_score=validated.confidence,
            match_type=validated.match_type,
            needs_review=True,  # All utilities require manual review
            review_reason=validated.review_reason,
        )
        db.add(hu)

    def _link_docket_validated(self, hearing: Hearing, validated: ValidatedDocket, db: Session) -> Tuple[Optional[Docket], bool]:
        """Link validated docket to dockets table. Returns (docket, was_created)."""
        if not validated.docket_number:
            return None, False

        state_code = hearing.state.code if hearing.state else None

        # Check for existing docket
        docket = db.query(Docket).filter(Docket.normalized_id == validated.normalized_name).first()

        if docket:
            docket.last_mentioned_at = datetime.now(timezone.utc)
            docket.mention_count = (docket.mention_count or 0) + 1
            created = False
        else:
            # Create new docket
            docket = Docket(
                state_id=hearing.state_id,
                docket_number=validated.docket_number,
                normalized_id=validated.normalized_name,
                first_seen_at=datetime.now(timezone.utc),
                last_mentioned_at=datetime.now(timezone.utc),
                mention_count=1,
                year=validated.year,
                sector=validated.sector,
                confidence=validated.match_type if validated.match_type != 'none' else 'unverified',
                match_score=validated.match_score,
            )

            # Link to known docket if matched
            if validated.matched_id:
                docket.known_docket_id = validated.matched_id
                docket.title = validated.known_title
                docket.company = validated.known_utility

            db.add(docket)
            db.flush()
            created = True

            logger.info(f"Created new docket: {validated.normalized_name} (confidence={validated.confidence})")

        # Create HearingDocket junction - ALWAYS needs review per user requirement
        existing_hd = db.query(HearingDocket).filter(
            HearingDocket.hearing_id == hearing.id,
            HearingDocket.docket_id == docket.id
        ).first()

        if existing_hd:
            existing_hd.context_summary = validated.context
            existing_hd.confidence_score = validated.confidence
            existing_hd.match_type = validated.match_type
            existing_hd.needs_review = True  # Always needs review
            existing_hd.review_reason = validated.review_reason
        else:
            hd = HearingDocket(
                hearing_id=hearing.id,
                docket_id=docket.id,
                context_summary=validated.context,
                confidence_score=validated.confidence,
                match_type=validated.match_type,
                needs_review=True,  # Always needs review
                review_reason=validated.review_reason,
            )
            db.add(hd)

        return docket, created

    # ==================== Docket Matching Methods ====================

    def _load_known_dockets(self, state_code: str, db: Session) -> Dict[str, KnownDocket]:
        """Load known dockets for a state into cache."""
        if state_code not in self._known_dockets_cache:
            known = db.query(KnownDocket).filter(
                KnownDocket.state_code == state_code
            ).all()

            self._known_dockets_cache[state_code] = {
                normalize_for_matching(d.normalized_id): d
                for d in known
            }

        return self._known_dockets_cache[state_code]

    def _match_to_known_docket(
        self,
        docket: Docket,
        state_code: str,
        db: Session
    ) -> Tuple[Optional[KnownDocket], float, str]:
        """
        Match a docket to known dockets.

        Returns: (known_docket, score, confidence)
        Confidence levels: verified (exact), likely (>=0.85), possible (>=0.70), unverified
        """
        known_dockets = self._load_known_dockets(state_code, db)

        if not known_dockets:
            return None, 0.0, 'unverified'

        normalized = normalize_for_matching(docket.normalized_id)

        # Exact match
        if normalized in known_dockets:
            return known_dockets[normalized], 1.0, 'verified'

        # Fuzzy match (if rapidfuzz available)
        if FUZZY_AVAILABLE:
            matches = process.extractOne(
                normalized,
                known_dockets.keys(),
                scorer=fuzz.ratio,
                score_cutoff=70  # 0.70 threshold
            )

            if matches:
                matched_key, score, _ = matches
                score = score / 100.0

                if score >= 0.95:
                    confidence = 'verified'
                elif score >= 0.85:
                    confidence = 'likely'
                else:
                    confidence = 'possible'

                return known_dockets[matched_key], score, confidence

        return None, 0.0, 'unverified'

    def _enrich_docket_from_known(self, docket: Docket, known: KnownDocket):
        """Copy authoritative data from KnownDocket to Docket."""
        if known.utility_name and not docket.company:
            docket.company = known.utility_name
        if known.sector:
            docket.sector = known.sector
        if known.year:
            docket.year = known.year
        if known.title and not docket.title:
            docket.title = known.title

    def _normalize_docket_id(self, docket_number: str, state_code: Optional[str]) -> str:
        """Create normalized ID for docket (e.g., GA-44160)."""
        cleaned = re.sub(r'^(Docket|Case|Application|Project)\s*(No\.?\s*)?', '', docket_number, flags=re.IGNORECASE)
        cleaned = cleaned.strip()

        if state_code:
            return f"{state_code}-{cleaned}"
        return cleaned

    def _get_or_create_docket(self, docket_number: str, hearing: Hearing, docket_data: Dict[str, Any], db: Session) -> Optional[Docket]:
        """Get existing docket or create new one, with matching against known dockets."""
        state_code = hearing.state.code if hearing.state else None

        # Use docket parser to get structured data
        try:
            parsed = parse_docket(docket_number, state_code or 'XX')
            normalized_id = parsed.normalized_id
        except Exception:
            normalized_id = self._normalize_docket_id(docket_number, state_code)

        # Check for existing
        docket = db.query(Docket).filter(Docket.normalized_id == normalized_id).first()

        if docket:
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
            confidence='unverified',
        )

        # Set parsed fields if available
        try:
            parsed = parse_docket(docket_number, state_code or 'XX')
            if parsed.year:
                docket.year = parsed.year
            if parsed.utility_sector:
                docket.sector = parsed.utility_sector
        except Exception:
            pass

        db.add(docket)
        db.flush()

        # Match against known dockets (for confidence scoring and enrichment)
        if state_code:
            known, score, confidence = self._match_to_known_docket(docket, state_code, db)
            docket.confidence = confidence
            docket.match_score = score
            if known:
                docket.known_docket_id = known.id
                self._enrich_docket_from_known(docket, known)
                logger.info(f"Matched docket {normalized_id} to known docket (confidence={confidence}, score={score:.2f})")
            else:
                logger.info(f"Created new docket: {normalized_id} (unverified)")
        else:
            logger.info(f"Created new docket: {normalized_id} (no state for matching)")

        return docket

    def _link_docket(self, hearing: Hearing, docket_data: Dict[str, Any], db: Session) -> Tuple[Optional[Docket], bool]:
        """Create or get docket and link to hearing. Returns (docket, was_created)."""
        number = docket_data.get('number', '').strip()
        if not number:
            return None, False

        # Get or create the docket (includes matching against known dockets)
        docket = self._get_or_create_docket(number, hearing, docket_data, db)
        if not docket:
            return None, False

        # Check if HearingDocket link already exists
        existing = db.query(HearingDocket).filter(
            HearingDocket.hearing_id == hearing.id,
            HearingDocket.docket_id == docket.id
        ).first()

        if existing:
            if docket_data.get('context'):
                existing.context_summary = docket_data['context']
            # Ensure existing links are also flagged for review
            existing.needs_review = True
            return docket, False

        # Create HearingDocket junction record
        # Always set needs_review=True - all dockets require human verification
        hd = HearingDocket(
            hearing_id=hearing.id,
            docket_id=docket.id,
            context_summary=docket_data.get('context'),
            needs_review=True,
        )
        db.add(hd)

        return docket, True

    def on_error(self, hearing: Hearing, job: PipelineJob, result: StageResult, db: Session):
        """Clean up partial analysis on error."""
        analysis = db.query(Analysis).filter(Analysis.hearing_id == hearing.id).first()
        if analysis:
            db.delete(analysis)
            db.commit()
            logger.info(f"Cleaned up partial analysis for hearing {hearing.id}")
