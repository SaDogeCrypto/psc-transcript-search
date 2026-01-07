"""
Smart Docket Extraction Pipeline

Multi-stage pipeline that extracts docket candidates from transcripts,
validates them against known dockets, scores confidence, and suggests
corrections for transcription errors.

Stages:
1. Candidate Extraction - Regex with context capture
2. Format Validation - State-specific format rules
3. Known Docket Matching - Exact + fuzzy matching
4. Context Analysis - Trigger phrases, entity co-occurrence
5. Confidence Scoring - Weighted combination
6. Correction Suggestion - Evidence-based suggestions
7. Storage - Route to accepted/review/rejected
"""

import re
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class FuzzyMatch:
    """A fuzzy match candidate from known dockets."""
    docket_id: int
    docket_number: str
    title: Optional[str]
    distance: int
    score: int
    error_type: str  # "digit_drop", "transposition", "substitution", "other"


@dataclass
class CandidateDocket:
    """A candidate docket extraction with validation results."""
    # Extraction
    raw_text: str
    normalized_id: str
    state_code: str
    context_before: str = ""
    context_after: str = ""
    trigger_phrase: str = ""
    position: int = 0

    # Format validation
    format_valid: bool = False
    format_score: int = 0
    format_issues: List[str] = field(default_factory=list)

    # Known docket matching
    match_type: str = "none"  # exact, fuzzy, none
    matched_docket_id: Optional[int] = None
    matched_docket_number: Optional[str] = None
    matched_docket_title: Optional[str] = None
    fuzzy_score: int = 0
    fuzzy_candidates: List[FuzzyMatch] = field(default_factory=list)

    # Context analysis
    context_score: int = 0
    context_clues: List[str] = field(default_factory=list)

    # Final scoring
    confidence: int = 0
    status: str = "pending"  # pending, accepted, needs_review, rejected
    review_reason: str = ""

    # Correction suggestion
    suggested_docket_id: Optional[int] = None
    suggested_correction: Optional[str] = None
    correction_confidence: int = 0
    correction_evidence: List[str] = field(default_factory=list)


# =============================================================================
# State-Specific Format Rules
# =============================================================================

STATE_DOCKET_RULES = {
    "TX": {
        "patterns": [
            (r'\b(\d{5})\b', "5-digit number"),
            # Also capture 4-digit numbers after trigger phrases (may be truncated)
            (r'(?:docket|project|case)\s*(?:number|no\.?|#)?\s*(\d{4,5})\b', "triggered number"),
        ],
        "validators": [
            ("length", lambda x: len(re.sub(r'\D', '', x)) == 5, "Must be exactly 5 digits"),
            ("range", lambda x: 10000 <= int(re.sub(r'\D', '', x)) <= 99999, "Must be in valid range"),
        ],
        "description": "5-digit number (e.g., 55999)",
    },
    "FL": {
        "patterns": [
            (r'\b(20\d{2}-\d{4}-[A-Z]{2})\b', "YYYY-NNNN-XX format (e.g., 2024-0190-EI)"),
            (r'\b(\d{8}-[A-Z]{2})\b', "YYYYNNNN-XX format (e.g., 20240190-EI)"),
        ],
        "validators": [
            ("format", lambda x: bool(re.match(r'^20\d{2}-?\d{4}-[A-Z]{2}$', x)), "Must match FL docket format"),
            ("year", lambda x: 2000 <= int(x[:4]) <= 2030 if len(x) >= 4 else False, "Year must be 2000-2030"),
        ],
        "description": "YYYY-NNNN-XX (e.g., 2024-0190-EI)",
    },
    "CA": {
        "patterns": [
            (r'\b([ARCIP]\.\d{2}-\d{2}-\d{3})\b', "X.YY-MM-NNN format"),
            (r'\b([ARCIP])(\d{2})(\d{2})(\d{3})\b', "Compact format"),
        ],
        "validators": [
            ("format", lambda x: bool(re.match(r'^[ARCIP]\.\d{2}-\d{2}-\d{3}$', x)), "Must match X.YY-MM-NNN"),
            ("month", lambda x: 1 <= int(x.split('-')[1]) <= 12 if '-' in x else True, "Month must be 01-12"),
        ],
        "description": "X.YY-MM-NNN (e.g., A.25-07-003)",
    },
    "GA": {
        "patterns": [
            (r'\b(\d{5})\b', "5-digit number"),
        ],
        "validators": [
            ("length", lambda x: len(re.sub(r'\D', '', x)) == 5, "Must be exactly 5 digits"),
            ("range", lambda x: 30000 <= int(re.sub(r'\D', '', x)) <= 60000, "Must be in typical GA range"),
        ],
        "description": "5-digit number (e.g., 44280)",
    },
    "OH": {
        "patterns": [
            (r'\b(\d{2}-\d{4}-[A-Z]{2}-[A-Z]{2,3})\b', "YY-NNNN-XX-XXX format"),
        ],
        "validators": [
            ("format", lambda x: bool(re.match(r'^\d{2}-\d{4}-[A-Z]{2}-[A-Z]{2,3}$', x)), "Must match YY-NNNN-XX-XXX"),
        ],
        "description": "YY-NNNN-XX-XXX (e.g., 25-0594-EL-AIR)",
    },
    "AZ": {
        "patterns": [
            # Arizona format: L-NNNNN[A]-YY-NNNN (e.g., T-21349A-25-0016)
            (r'\b([A-Z]-\d{5}[A-Z]?-\d{2}-\d{4})\b', "Arizona full docket format"),
            # Partial format: YY-NNNN
            (r'\b(\d{2}-\d{4})\b', "Arizona short format"),
        ],
        "validators": [
            ("format", lambda x: bool(re.match(r'^[A-Z]-\d{5}[A-Z]?-\d{2}-\d{4}$', x) or re.match(r'^\d{2}-\d{4}$', x)), "Must match AZ format"),
        ],
        "description": "L-NNNNN[A]-YY-NNNN (e.g., T-21349A-25-0016)",
    },
}

# Generic patterns for states without specific rules
GENERIC_PATTERNS = [
    (r'\b(\d{2}-\d{3,6}(?:-[A-Z]{2,3})?)\b', "Generic YY-NNNN format"),
    (r'\b(Docket\s*(?:No\.?\s*)?[\d-]+)\b', "Docket No. format"),
    (r'\b(Case\s*(?:No\.?\s*)?[\d-]+)\b', "Case No. format"),
    (r'\b(Project\s*(?:No\.?\s*)?[\d-]+)\b', "Project No. format"),
]


# =============================================================================
# Context Scoring Rules
# =============================================================================

# Trigger phrases with confidence scores
TRIGGER_PHRASES = [
    (r'docket\s*(?:number|no\.?|#)\s*$', 40, "docket number"),
    (r'project\s*(?:number|no\.?|#)\s*$', 40, "project number"),
    (r'case\s*(?:number|no\.?|#)\s*$', 35, "case number"),
    (r'proceeding\s*(?:number|no\.?|#)\s*$', 35, "proceeding number"),
    (r'application\s*(?:number|no\.?|#)?\s*$', 30, "application"),
    (r'item\s*(?:number\s*)?\d+[,.\s]*(?:that\'?s?|is|--)\s*(?:project|docket)?\s*(?:number)?\s*$', 25, "agenda item reference"),
    (r'(?:in|under|for|re:?)\s*(?:docket|case|project)?\s*$', 20, "reference phrase"),
]

# Context boosters - terms that increase confidence
CONTEXT_BOOSTERS = [
    (r'\b(duke\s*energy|dominion|firstenergy|aep|ercot|oncor|centerpoint|georgia\s*power|pge|sce|sdge)\b', 15, "utility name"),
    (r'\b(rate\s*case|rate\s*increase|tariff|rate\s*filing|rate\s*adjustment)\b', 12, "rate case language"),
    (r'\b(commission|puc|puct|psc|cpuc|fpsc|gpsc|hearing|testimony|witness)\b', 10, "regulatory language"),
    (r'\b(application|petition|complaint|rulemaking|investigation)\b', 10, "filing type"),
    (r'\b(electric|gas|water|telecom|utility|service)\b', 8, "sector reference"),
]


# =============================================================================
# Smart Extraction Pipeline
# =============================================================================

class SmartExtractionPipeline:
    """
    Multi-stage pipeline for intelligent docket extraction.
    """

    # Confidence thresholds
    ACCEPT_THRESHOLD = 80
    REVIEW_THRESHOLD = 50

    # Confidence weights
    WEIGHTS = {
        'format': 0.20,
        'match': 0.45,
        'context': 0.25,
        'fuzzy_bonus': 0.10,
    }

    def __init__(self, db: Session):
        self.db = db
        self._known_dockets_cache: Dict[str, List] = {}

    def process_transcript(
        self,
        text: str,
        state_code: str,
        hearing_id: int
    ) -> List[CandidateDocket]:
        """
        Process a transcript through all pipeline stages.

        Args:
            text: Full transcript text
            state_code: Two-letter state code
            hearing_id: ID of the hearing

        Returns:
            List of CandidateDocket objects with full validation
        """
        candidates = []

        # Stage 1: Extract candidates
        raw_candidates = self._extract_candidates(text, state_code)
        logger.info(f"Stage 1: Extracted {len(raw_candidates)} candidates from transcript")

        for candidate in raw_candidates:
            # Stage 2: Format validation
            self._validate_format(candidate)

            # Stage 3: Known docket matching
            self._match_known_dockets(candidate)

            # Stage 4: Context analysis
            self._analyze_context(candidate)

            # Stage 5: Confidence scoring
            self._calculate_confidence(candidate)

            # Stage 6: Correction suggestions
            self._suggest_corrections(candidate)

            candidates.append(candidate)

        # Deduplicate by normalized_id, keeping highest confidence
        candidates = self._deduplicate(candidates)

        logger.info(f"Pipeline complete: {len(candidates)} unique candidates")
        for c in candidates:
            logger.info(f"  {c.normalized_id}: confidence={c.confidence}, status={c.status}")

        return candidates

    # -------------------------------------------------------------------------
    # Stage 1: Candidate Extraction
    # -------------------------------------------------------------------------

    def _extract_candidates(self, text: str, state_code: str) -> List[CandidateDocket]:
        """Extract candidate docket numbers with context."""
        candidates = []
        seen_positions = set()

        # Get patterns for this state
        patterns = []
        if state_code in STATE_DOCKET_RULES:
            patterns.extend(STATE_DOCKET_RULES[state_code]["patterns"])
        patterns.extend(GENERIC_PATTERNS)

        for pattern, pattern_desc in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                pos = match.start()

                # Skip if we already found something at this position
                if any(abs(pos - p) < 5 for p in seen_positions):
                    continue

                raw_text = match.group(1) if match.lastindex else match.group(0)

                # Clean up raw text
                raw_text = self._clean_docket_number(raw_text)
                if not raw_text or len(raw_text) < 4:
                    continue

                seen_positions.add(pos)

                # Capture context
                context_start = max(0, pos - 80)
                context_end = min(len(text), match.end() + 80)
                context_before = text[context_start:pos].strip()
                context_after = text[match.end():context_end].strip()

                # Detect trigger phrase
                trigger = self._detect_trigger_phrase(context_before)

                # Create normalized ID
                normalized = self._normalize_docket_id(raw_text, state_code)

                candidates.append(CandidateDocket(
                    raw_text=raw_text,
                    normalized_id=normalized,
                    state_code=state_code,
                    context_before=context_before,
                    context_after=context_after,
                    trigger_phrase=trigger,
                    position=pos,
                ))

        return candidates

    def _clean_docket_number(self, raw: str) -> str:
        """Clean up extracted docket number."""
        # Remove common prefixes
        cleaned = re.sub(
            r'^(Docket|Case|Application|Project|Proceeding)\s*(No\.?\s*)?',
            '', raw, flags=re.IGNORECASE
        )
        return cleaned.strip()

    def _normalize_docket_id(self, docket_number: str, state_code: str) -> str:
        """Create normalized ID (e.g., TX-55999)."""
        cleaned = self._clean_docket_number(docket_number)
        return f"{state_code}-{cleaned}"

    def _detect_trigger_phrase(self, context_before: str) -> str:
        """Detect if context ends with a trigger phrase."""
        context_lower = context_before.lower()
        for pattern, score, name in TRIGGER_PHRASES:
            if re.search(pattern, context_lower, re.IGNORECASE):
                return name
        return ""

    # -------------------------------------------------------------------------
    # Stage 2: Format Validation
    # -------------------------------------------------------------------------

    def _validate_format(self, candidate: CandidateDocket):
        """Validate docket format against state-specific rules."""
        state_code = candidate.state_code
        raw = candidate.raw_text

        if state_code not in STATE_DOCKET_RULES:
            # No specific rules - give moderate score
            candidate.format_valid = True
            candidate.format_score = 50
            return

        rules = STATE_DOCKET_RULES[state_code]
        issues = []
        passed = 0
        total = len(rules["validators"])

        for name, validator, message in rules["validators"]:
            try:
                if validator(raw):
                    passed += 1
                else:
                    issues.append(f"{name}: {message}")
            except (ValueError, IndexError, TypeError):
                issues.append(f"{name}: validation error")

        candidate.format_valid = len(issues) == 0
        candidate.format_score = int((passed / max(total, 1)) * 100)
        candidate.format_issues = issues

    # -------------------------------------------------------------------------
    # Stage 3: Known Docket Matching
    # -------------------------------------------------------------------------

    def _match_known_dockets(self, candidate: CandidateDocket):
        """Match against known dockets with exact and fuzzy matching."""
        from app.models.database import KnownDocket

        state_code = candidate.state_code

        # Load known dockets for this state (with caching)
        if state_code not in self._known_dockets_cache:
            known = self.db.query(KnownDocket).filter(
                KnownDocket.state_code == state_code
            ).all()
            self._known_dockets_cache[state_code] = known

        known_dockets = self._known_dockets_cache[state_code]

        # Check for exact match
        for known in known_dockets:
            if self._is_exact_match(candidate.raw_text, known.docket_number):
                candidate.match_type = "exact"
                candidate.matched_docket_id = known.id
                candidate.matched_docket_number = known.docket_number
                candidate.matched_docket_title = known.title
                candidate.fuzzy_score = 100
                return

        # No exact match - try fuzzy matching
        context = f"{candidate.context_before} {candidate.context_after}".lower()
        fuzzy_matches = self._find_fuzzy_matches(candidate.raw_text, known_dockets, context)

        if fuzzy_matches:
            candidate.fuzzy_candidates = fuzzy_matches
            best = fuzzy_matches[0]

            if best.score >= 80:
                candidate.match_type = "fuzzy"
                candidate.matched_docket_id = best.docket_id
                candidate.matched_docket_number = best.docket_number
                candidate.matched_docket_title = best.title
                candidate.fuzzy_score = best.score

    def _is_exact_match(self, extracted: str, known: str) -> bool:
        """Check if extracted matches known docket exactly."""
        # Normalize both for comparison
        e = re.sub(r'[^a-zA-Z0-9]', '', extracted.upper())
        k = re.sub(r'[^a-zA-Z0-9]', '', known.upper())
        return e == k

    def _find_fuzzy_matches(
        self,
        extracted: str,
        known_dockets: List,
        context: str = ""
    ) -> List[FuzzyMatch]:
        """Find fuzzy matches using Levenshtein distance with context boosting."""
        matches = []
        extracted_clean = re.sub(r'[^0-9]', '', extracted)
        context_words = set(context.lower().split()) - {'the', 'of', 'and', 'a', 'an', 'in', 'for', 'to', 'is', 'that'}

        for known in known_dockets:
            known_clean = re.sub(r'[^0-9]', '', known.docket_number)

            # Calculate distance
            distance = self._levenshtein_distance(extracted_clean, known_clean)

            # Check for specific error patterns
            error_type = "other"
            if self._is_missing_digit(extracted_clean, known_clean):
                error_type = "digit_drop"
                distance = min(distance, 1)  # Treat as distance 1
            elif self._is_digit_transposition(extracted_clean, known_clean):
                error_type = "transposition"
                distance = min(distance, 1)

            # Only include close matches
            if distance <= 2:
                score = max(0, 100 - (distance * 25))
                if error_type == "digit_drop":
                    score = min(100, score + 15)  # Boost for common STT error

                # Context boost: if title words appear in context, boost score
                if known.title and context_words:
                    title_words = set(known.title.lower().split()) - {'the', 'of', 'and', 'a', 'an', 'in', 'for', 'to'}
                    overlap = context_words & title_words
                    if overlap:
                        # Significant boost for context match
                        context_boost = min(20, len(overlap) * 8)
                        score = min(100, score + context_boost)
                        error_type = f"{error_type}+context"

                matches.append(FuzzyMatch(
                    docket_id=known.id,
                    docket_number=known.docket_number,
                    title=known.title,
                    distance=distance,
                    score=score,
                    error_type=error_type,
                ))

        # Sort by score descending
        return sorted(matches, key=lambda x: x.score, reverse=True)[:5]

    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """Calculate Levenshtein edit distance."""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        prev_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            curr_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = prev_row[j + 1] + 1
                deletions = curr_row[j] + 1
                substitutions = prev_row[j] + (c1 != c2)
                curr_row.append(min(insertions, deletions, substitutions))
            prev_row = curr_row

        return prev_row[-1]

    def _is_missing_digit(self, short: str, long: str) -> bool:
        """Check if short is long with one digit missing."""
        if len(long) - len(short) != 1:
            return False
        # Try removing each digit from long
        for i in range(len(long)):
            if long[:i] + long[i+1:] == short:
                return True
        return False

    def _is_digit_transposition(self, s1: str, s2: str) -> bool:
        """Check if s1 and s2 differ by a single transposition."""
        if len(s1) != len(s2):
            return False
        diffs = [(i, c1, c2) for i, (c1, c2) in enumerate(zip(s1, s2)) if c1 != c2]
        if len(diffs) != 2:
            return False
        i, j = diffs[0][0], diffs[1][0]
        return j == i + 1 and s1[i] == s2[j] and s1[j] == s2[i]

    # -------------------------------------------------------------------------
    # Stage 4: Context Analysis
    # -------------------------------------------------------------------------

    def _analyze_context(self, candidate: CandidateDocket):
        """Analyze surrounding context to score confidence."""
        score = 0
        clues = []

        context_before = candidate.context_before.lower()
        context_after = candidate.context_after.lower()
        full_context = f"{context_before} {context_after}"

        # Score trigger phrases
        for pattern, points, name in TRIGGER_PHRASES:
            if re.search(pattern, context_before, re.IGNORECASE):
                score += points
                clues.append(f"trigger: {name}")
                break  # Only count best trigger

        # Score context boosters
        for pattern, points, name in CONTEXT_BOOSTERS:
            if re.search(pattern, full_context, re.IGNORECASE):
                score += points
                clues.append(f"context: {name}")

        # Bonus if context matches known docket title
        if candidate.matched_docket_title:
            title_words = set(candidate.matched_docket_title.lower().split())
            context_words = set(full_context.split())
            overlap = title_words & context_words
            # Remove common words
            overlap -= {'the', 'of', 'and', 'a', 'an', 'in', 'for', 'to'}
            if len(overlap) >= 2:
                score += 15
                clues.append(f"title_match: {overlap}")

        candidate.context_score = min(score, 100)
        candidate.context_clues = clues

    # -------------------------------------------------------------------------
    # Stage 5: Confidence Scoring
    # -------------------------------------------------------------------------

    def _calculate_confidence(self, candidate: CandidateDocket):
        """Calculate final confidence score and status."""

        # EXACT MATCH TO KNOWN DOCKET = AUTO-ACCEPT
        # If we have an exact match to a known docket, accept it regardless of format/context
        # The format may be "incomplete" (e.g., "21-902" instead of "21-902-EL-RDR") but
        # if it matches a known docket, that's good enough
        if candidate.match_type == "exact":
            candidate.confidence = 95  # High confidence
            candidate.status = "accepted"
            return

        # Check for "new docket candidate" - valid format + good context but no known match
        # These should be flagged for review, not rejected
        is_new_docket_candidate = (
            candidate.format_valid and
            candidate.context_score >= 30 and  # Has a trigger phrase
            candidate.match_type == "none"
        )

        if is_new_docket_candidate:
            # For new docket candidates, use format + context only (no match penalty)
            confidence = (
                candidate.format_score * 0.40 +
                candidate.context_score * 0.60
            )
            candidate.confidence = int(min(100, confidence))
            candidate.status = "needs_review"
            candidate.review_reason = "New docket candidate (not in known_dockets)"
            return

        # Standard weighted scoring for matched or invalid format cases
        confidence = (
            candidate.format_score * self.WEIGHTS['format'] +
            candidate.fuzzy_score * self.WEIGHTS['match'] +
            candidate.context_score * self.WEIGHTS['context']
        )

        # Fuzzy bonus if we have a fuzzy match
        if candidate.match_type == "fuzzy" and candidate.fuzzy_score >= 70:
            confidence += candidate.fuzzy_score * self.WEIGHTS['fuzzy_bonus']

        candidate.confidence = int(min(100, confidence))

        # Determine status
        if candidate.confidence >= self.ACCEPT_THRESHOLD:
            candidate.status = "accepted"
        elif candidate.confidence >= self.REVIEW_THRESHOLD:
            candidate.status = "needs_review"
            candidate.review_reason = self._build_review_reason(candidate)
        else:
            candidate.status = "rejected"
            candidate.review_reason = self._build_review_reason(candidate)

    def _build_review_reason(self, candidate: CandidateDocket) -> str:
        """Build human-readable review reason."""
        reasons = []

        if not candidate.format_valid:
            reasons.append(f"Format invalid ({', '.join(candidate.format_issues)})")

        if candidate.match_type == "none":
            reasons.append("No match in known dockets")
        elif candidate.match_type == "fuzzy":
            reasons.append(f"Fuzzy match to {candidate.matched_docket_number}")

        if candidate.context_score < 30:
            reasons.append("Low context confidence")

        return "; ".join(reasons) if reasons else "Low overall confidence"

    # -------------------------------------------------------------------------
    # Stage 6: Correction Suggestions
    # -------------------------------------------------------------------------

    def _suggest_corrections(self, candidate: CandidateDocket):
        """Suggest corrections based on fuzzy matches and context.

        IMPORTANT: Only suggest a correction if the context actually supports it.
        A digit transposition to a known docket is only valid if the known docket's
        title/company matches what's being discussed in the transcript.
        """
        if candidate.match_type == "exact":
            return  # No correction needed

        if not candidate.fuzzy_candidates:
            return  # No suggestions available

        best = candidate.fuzzy_candidates[0]
        evidence = []
        context_supports = False

        # Combine all context for checking
        full_context = f"{candidate.context_before} {candidate.context_after}".lower()
        # Extensive stop word list - these don't indicate a real match
        stop_words = {
            'the', 'of', 'and', 'a', 'an', 'in', 'for', 'to', 'is', 'this', 'that',
            'on', 'at', 'by', 'with', 'from', 'as', 'or', 'be', 'are', 'was', 'were',
            'it', 'its', 'we', 'our', 'they', 'their', 'he', 'she', 'his', 'her',
            'item', 'number', 'case', 'docket', 'project', 'under', 'section',
            'order', 'motion', 'approved', 'all', 'will', 'can', 'may', 'shall',
            'has', 'have', 'had', 'been', 'being', 'would', 'could', 'should',
            'not', 'no', 'yes', 'any', 'each', 'every', 'some', 'other',
            'first', 'second', 'third', 'next', 'last', 'new', 'old',
        }
        context_words = set(full_context.split()) - stop_words

        # Check if context supports this correction
        if best.title:
            # Extract significant words from the known docket title
            title_stop_words = {
                'the', 'of', 'and', 'a', 'an', 'in', 'for', 'to', 'on', 'at', 'by',
                'inc', 'llc', 'corp', 'company', 'co', 'corporation', 'limited',
                'application', 'complaint', 'petition', 'request', 'filing', 'case',
                'against', 'regarding', 'concerning', 're', 'matter',
            }
            title_words = set(best.title.lower().split()) - title_stop_words
            overlap = title_words & context_words

            # Require at least one MEANINGFUL word overlap (not just common words)
            if overlap and len(overlap) >= 1:
                # At least one significant word from the title appears in context
                context_supports = True
                evidence.append(f"Context matches title: {overlap}")
            elif len(title_words) > 0:
                # Title has words but none match context - this is likely a BAD suggestion
                logger.debug(f"Skipping suggestion {best.docket_number} - title '{best.title}' doesn't match context")
                return  # Don't suggest this correction

        # Build evidence for the error type
        if best.error_type == "digit_drop":
            evidence.append(f"Missing digit pattern: {candidate.raw_text} → {best.docket_number}")
        elif best.error_type == "transposition":
            evidence.append(f"Digit transposition: {candidate.raw_text} → {best.docket_number}")
        elif best.error_type and "context" in best.error_type:
            # Context-boosted match - already validated
            context_supports = True

        if best.title:
            evidence.append(f"Known docket: '{best.title}'")

        # Only suggest if we have context support OR the format is clearly invalid
        # (e.g., wrong number of digits which strongly suggests transcription error)
        format_clearly_wrong = not candidate.format_valid and "length" in str(candidate.format_issues)

        if context_supports or format_clearly_wrong:
            candidate.suggested_docket_id = best.docket_id
            candidate.suggested_correction = best.docket_number
            # Reduce confidence if no context support
            candidate.correction_confidence = best.score if context_supports else max(40, best.score - 30)
            candidate.correction_evidence = evidence
        else:
            # No suggestion - context doesn't support it
            logger.debug(f"No suggestion for {candidate.raw_text} - no context support for {best.docket_number}")

    # -------------------------------------------------------------------------
    # Deduplication
    # -------------------------------------------------------------------------

    def _deduplicate(self, candidates: List[CandidateDocket]) -> List[CandidateDocket]:
        """Deduplicate candidates, keeping highest confidence.

        Handles cases like "21-902" vs "21-902-" being the same docket.
        """
        seen = {}
        for c in candidates:
            # Normalize key by stripping trailing punctuation
            key = c.normalized_id.rstrip('-').rstrip('.')
            if key not in seen or c.confidence > seen[key].confidence:
                seen[key] = c
        return list(seen.values())

    # -------------------------------------------------------------------------
    # Storage
    # -------------------------------------------------------------------------

    def store_candidates(
        self,
        candidates: List[CandidateDocket],
        hearing_id: int
    ) -> Dict[str, int]:
        """
        Store candidates in extracted_dockets table.

        Returns:
            Dict with counts: {accepted, needs_review, rejected}
        """
        from sqlalchemy import text

        counts = {"accepted": 0, "needs_review": 0, "rejected": 0}

        for candidate in candidates:
            # Prepare JSON fields
            format_issues = json.dumps(candidate.format_issues) if candidate.format_issues else None
            fuzzy_candidates = json.dumps([asdict(f) for f in candidate.fuzzy_candidates]) if candidate.fuzzy_candidates else None
            context_clues = json.dumps(candidate.context_clues) if candidate.context_clues else None
            correction_evidence = json.dumps(candidate.correction_evidence) if candidate.correction_evidence else None

            self.db.execute(text("""
                INSERT INTO extracted_dockets (
                    hearing_id, raw_text, normalized_id,
                    context_before, context_after, trigger_phrase, transcript_position,
                    format_valid, format_score, format_issues,
                    match_type, matched_known_docket_id, fuzzy_score, fuzzy_candidates,
                    context_score, context_clues,
                    confidence_score, status, review_reason,
                    suggested_docket_id, suggested_correction, correction_confidence, correction_evidence
                ) VALUES (
                    :hearing_id, :raw_text, :normalized_id,
                    :context_before, :context_after, :trigger_phrase, :position,
                    :format_valid, :format_score, :format_issues,
                    :match_type, :matched_docket_id, :fuzzy_score, :fuzzy_candidates,
                    :context_score, :context_clues,
                    :confidence, :status, :review_reason,
                    :suggested_docket_id, :suggested_correction, :correction_confidence, :correction_evidence
                )
            """), {
                "hearing_id": hearing_id,
                "raw_text": candidate.raw_text,
                "normalized_id": candidate.normalized_id,
                "context_before": candidate.context_before,
                "context_after": candidate.context_after,
                "trigger_phrase": candidate.trigger_phrase,
                "position": candidate.position,
                "format_valid": candidate.format_valid,
                "format_score": candidate.format_score,
                "format_issues": format_issues,
                "match_type": candidate.match_type,
                "matched_docket_id": candidate.matched_docket_id,
                "fuzzy_score": candidate.fuzzy_score,
                "fuzzy_candidates": fuzzy_candidates,
                "context_score": candidate.context_score,
                "context_clues": context_clues,
                "confidence": candidate.confidence,
                "status": candidate.status,
                "review_reason": candidate.review_reason,
                "suggested_docket_id": candidate.suggested_docket_id,
                "suggested_correction": candidate.suggested_correction,
                "correction_confidence": candidate.correction_confidence,
                "correction_evidence": correction_evidence,
            })

            counts[candidate.status] = counts.get(candidate.status, 0) + 1

        self.db.commit()
        return counts
