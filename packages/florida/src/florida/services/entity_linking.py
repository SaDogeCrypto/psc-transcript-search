"""
Florida Entity Linking Service.

Extracts entities from transcripts and links them to canonical records:
- Dockets: Regex extraction + fuzzy match to fl_dockets
- Utilities: LLM extraction + fuzzy match to fl_utilities
- Topics: LLM extraction + fuzzy match to fl_topics

Uses RapidFuzz for fuzzy matching with confidence scoring.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import func

logger = logging.getLogger(__name__)

# Try to import rapidfuzz, fall back to fuzzywuzzy
try:
    from rapidfuzz import fuzz, process
    FUZZY_LIB = "rapidfuzz"
except ImportError:
    try:
        from fuzzywuzzy import fuzz, process
        FUZZY_LIB = "fuzzywuzzy"
    except ImportError:
        fuzz = None
        process = None
        FUZZY_LIB = None
        logger.warning("No fuzzy matching library available. Install rapidfuzz or fuzzywuzzy.")


# Florida docket pattern: YYYYNNNN-XX (e.g., 20240190-EI)
FL_DOCKET_PATTERN = re.compile(
    r'\b(20[0-2][0-9])[\s\-]?([0-9]{4,5})[\s\-]?([A-Z]{2})\b',
    re.IGNORECASE
)

# Alternate patterns for spoken docket numbers
FL_DOCKET_SPOKEN_PATTERNS = [
    # "docket number 2024-0190-EI" or "docket 20240190EI"
    re.compile(r'docket\s*(?:number|no\.?)?\s*:?\s*(20[0-2][0-9])[\s\-]?([0-9]{4,5})[\s\-]?([A-Z]{2})', re.IGNORECASE),
    # "in case 20240190"
    re.compile(r'(?:in\s+)?case\s*(?:number|no\.?)?\s*:?\s*(20[0-2][0-9])[\s\-]?([0-9]{4,5})[\s\-]?([A-Z]{2})?', re.IGNORECASE),
]

# Confidence thresholds
THRESHOLDS = {
    'docket_exact': 95,
    'docket_fuzzy_accept': 85,
    'docket_fuzzy_review': 60,
    'utility_exact': 95,
    'utility_fuzzy_accept': 85,
    'utility_fuzzy_review': 70,
    'topic_exact': 90,
    'topic_fuzzy_accept': 80,
    'topic_fuzzy_review': 50,
}


@dataclass
class ExtractedDocket:
    """A docket number extracted from transcript."""
    raw_text: str
    normalized: str  # YYYYNNNN-XX format
    year: str
    sequence: str
    suffix: str
    context: str = ""  # Surrounding text
    position: int = 0  # Character position in transcript


@dataclass
class MatchedEntity:
    """Result of matching an extracted entity to canonical record."""
    entity_type: str  # docket, utility, topic
    extracted_text: str
    matched_id: Optional[int] = None
    matched_name: Optional[str] = None
    match_type: str = "none"  # exact, fuzzy, new, none
    match_score: float = 0.0
    confidence_score: float = 0.0
    needs_review: bool = True
    review_reason: str = ""
    context: str = ""
    role: Optional[str] = None  # For utilities: applicant, intervenor, subject
    relevance: Optional[str] = None  # For topics: high, medium, low
    sentiment: Optional[str] = None  # For topics


@dataclass
class EntityLinkingResult:
    """Results from entity linking for a hearing."""
    hearing_id: int
    dockets: List[MatchedEntity] = field(default_factory=list)
    utilities: List[MatchedEntity] = field(default_factory=list)
    topics: List[MatchedEntity] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def total_entities(self) -> int:
        return len(self.dockets) + len(self.utilities) + len(self.topics)

    @property
    def needs_review_count(self) -> int:
        return sum(1 for e in self.dockets + self.utilities + self.topics if e.needs_review)


class FloridaEntityLinker:
    """
    Links extracted entities to canonical Florida records.

    Process:
    1. Extract docket numbers from transcript using regex
    2. Get utilities/topics from LLM analysis (if available)
    3. Fuzzy match all entities against canonical records
    4. Calculate confidence scores
    5. Create junction table entries
    """

    def __init__(self, db: Session):
        self.db = db
        self._utilities_cache: Optional[List[Dict]] = None
        self._topics_cache: Optional[List[Dict]] = None
        self._dockets_cache: Optional[Dict[str, Dict]] = None

    def link_hearing(
        self,
        hearing_id: int,
        transcript_text: Optional[str] = None,
        analysis_data: Optional[Dict] = None,
        skip_existing: bool = True
    ) -> EntityLinkingResult:
        """
        Extract and link entities for a hearing.

        Args:
            hearing_id: ID of the hearing to process
            transcript_text: Full transcript text (optional, will load from DB)
            analysis_data: LLM analysis data with utilities/topics (optional)
            skip_existing: Skip if links already exist

        Returns:
            EntityLinkingResult with all matched entities
        """
        from florida.models import FLHearing, FLAnalysis
        from florida.models.linking import FLHearingDocket, FLHearingUtility, FLHearingTopic

        result = EntityLinkingResult(hearing_id=hearing_id)

        # Load hearing
        hearing = self.db.query(FLHearing).filter(FLHearing.id == hearing_id).first()
        if not hearing:
            result.errors.append(f"Hearing {hearing_id} not found")
            return result

        # Check for existing links
        if skip_existing:
            existing_dockets = self.db.query(FLHearingDocket).filter(
                FLHearingDocket.hearing_id == hearing_id
            ).count()
            existing_utilities = self.db.query(FLHearingUtility).filter(
                FLHearingUtility.hearing_id == hearing_id
            ).count()
            existing_topics = self.db.query(FLHearingTopic).filter(
                FLHearingTopic.hearing_id == hearing_id
            ).count()

            if existing_dockets > 0 or existing_utilities > 0 or existing_topics > 0:
                logger.info(f"Hearing {hearing_id} already has links, skipping")
                return result

        # Get transcript text
        if not transcript_text:
            transcript_text = hearing.full_text or ""
            if not transcript_text:
                # Try to build from segments
                from florida.models.hearing import FLTranscriptSegment
                segments = self.db.query(FLTranscriptSegment).filter(
                    FLTranscriptSegment.hearing_id == hearing_id
                ).order_by(FLTranscriptSegment.segment_index).all()
                transcript_text = "\n".join(s.text for s in segments if s.text)

        # Get analysis data
        if not analysis_data:
            analysis = self.db.query(FLAnalysis).filter(
                FLAnalysis.hearing_id == hearing_id
            ).first()
            if analysis:
                # Try utilities_extracted first, then fall back to utility_name field
                utilities = analysis.utilities_extracted or []
                if not utilities and analysis.utility_name:
                    # Convert single utility_name to expected format
                    utilities = [{'name': analysis.utility_name, 'role': 'applicant', 'context': ''}]

                # Try topics_extracted first, then check for topics in the JSON fields
                topics = analysis.topics_extracted or []

                analysis_data = {
                    'utilities': utilities,
                    'topics': topics,
                }

        # Extract and match dockets
        try:
            result.dockets = self._extract_and_match_dockets(
                transcript_text,
                hearing.docket_number
            )
        except Exception as e:
            logger.exception(f"Error extracting dockets for hearing {hearing_id}")
            result.errors.append(f"Docket extraction error: {e}")

        # Match utilities from analysis
        if analysis_data and analysis_data.get('utilities'):
            try:
                result.utilities = self._match_utilities(analysis_data['utilities'])
            except Exception as e:
                logger.exception(f"Error matching utilities for hearing {hearing_id}")
                result.errors.append(f"Utility matching error: {e}")

        # Match topics from analysis
        if analysis_data and analysis_data.get('topics'):
            try:
                result.topics = self._match_topics(analysis_data['topics'])
            except Exception as e:
                logger.exception(f"Error matching topics for hearing {hearing_id}")
                result.errors.append(f"Topic matching error: {e}")

        # Save links to database
        self._save_links(hearing_id, result)

        logger.info(
            f"Entity linking for hearing {hearing_id}: "
            f"{len(result.dockets)} dockets, {len(result.utilities)} utilities, "
            f"{len(result.topics)} topics ({result.needs_review_count} need review)"
        )

        return result

    def _extract_and_match_dockets(
        self,
        transcript_text: str,
        hearing_docket: Optional[str] = None
    ) -> List[MatchedEntity]:
        """Extract docket numbers from transcript and match to database."""
        from florida.models import FLDocket

        matches = []
        seen_dockets = set()

        # Extract docket numbers using regex
        extracted = self._extract_docket_numbers(transcript_text)

        # Include the hearing's own docket if set
        if hearing_docket:
            normalized = self._normalize_docket(hearing_docket)
            if normalized and normalized not in seen_dockets:
                extracted.insert(0, ExtractedDocket(
                    raw_text=hearing_docket,
                    normalized=normalized,
                    year=normalized[:4],
                    sequence=normalized[4:8],
                    suffix=normalized[9:] if len(normalized) > 9 else "",
                    context="Hearing docket number",
                    position=0
                ))

        # Load dockets cache
        if self._dockets_cache is None:
            self._load_dockets_cache()

        for ext in extracted:
            if ext.normalized in seen_dockets:
                continue
            seen_dockets.add(ext.normalized)

            # Try exact match first
            if ext.normalized in self._dockets_cache:
                cached = self._dockets_cache[ext.normalized]
                matches.append(MatchedEntity(
                    entity_type="docket",
                    extracted_text=ext.raw_text,
                    matched_id=cached['id'],
                    matched_name=cached['docket_number'],
                    match_type="exact",
                    match_score=100.0,
                    confidence_score=THRESHOLDS['docket_exact'],
                    needs_review=False,
                    review_reason="",
                    context=ext.context[:200] if ext.context else ""
                ))
                continue

            # Try fuzzy match
            fuzzy_result = self._fuzzy_match_docket(ext.normalized)
            if fuzzy_result:
                matched_id, matched_name, score = fuzzy_result
                confidence = self._calculate_docket_confidence(score, ext)
                needs_review = confidence < THRESHOLDS['docket_fuzzy_accept']

                matches.append(MatchedEntity(
                    entity_type="docket",
                    extracted_text=ext.raw_text,
                    matched_id=matched_id,
                    matched_name=matched_name,
                    match_type="fuzzy",
                    match_score=score,
                    confidence_score=confidence,
                    needs_review=needs_review,
                    review_reason=f"Fuzzy match ({score:.0f}%)" if needs_review else "",
                    context=ext.context[:200] if ext.context else ""
                ))
            else:
                # No match - might be a new docket or transcription error
                matches.append(MatchedEntity(
                    entity_type="docket",
                    extracted_text=ext.raw_text,
                    matched_id=None,
                    matched_name=None,
                    match_type="none",
                    match_score=0.0,
                    confidence_score=30.0,  # Low confidence for unmatched
                    needs_review=True,
                    review_reason="No match found in database",
                    context=ext.context[:200] if ext.context else ""
                ))

        return matches

    def _extract_docket_numbers(self, text: str) -> List[ExtractedDocket]:
        """Extract Florida docket numbers from text using regex."""
        extracted = []

        # Try spoken patterns first (more specific)
        for pattern in FL_DOCKET_SPOKEN_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()
                year = groups[0]
                sequence = groups[1].zfill(4)
                suffix = groups[2].upper() if groups[2] else "XX"

                normalized = f"{year}{sequence}-{suffix}"

                # Get context (50 chars before and after)
                start = max(0, match.start() - 50)
                end = min(len(text), match.end() + 50)
                context = text[start:end]

                extracted.append(ExtractedDocket(
                    raw_text=match.group(0),
                    normalized=normalized,
                    year=year,
                    sequence=sequence,
                    suffix=suffix,
                    context=context,
                    position=match.start()
                ))

        # General pattern
        for match in FL_DOCKET_PATTERN.finditer(text):
            year, sequence, suffix = match.groups()
            sequence = sequence.zfill(4)
            suffix = suffix.upper()

            normalized = f"{year}{sequence}-{suffix}"

            # Skip if already found
            if any(e.normalized == normalized for e in extracted):
                continue

            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end]

            extracted.append(ExtractedDocket(
                raw_text=match.group(0),
                normalized=normalized,
                year=year,
                sequence=sequence,
                suffix=suffix,
                context=context,
                position=match.start()
            ))

        return extracted

    def _normalize_docket(self, docket: str) -> Optional[str]:
        """Normalize a docket number to YYYYNNNN-XX format."""
        if not docket:
            return None

        # Try to match the pattern
        match = FL_DOCKET_PATTERN.search(docket)
        if match:
            year, sequence, suffix = match.groups()
            return f"{year}{sequence.zfill(4)}-{suffix.upper()}"

        # Try without suffix
        match = re.search(r'(20[0-2][0-9])[\s\-]?([0-9]{4,5})', docket)
        if match:
            year, sequence = match.groups()
            return f"{year}{sequence.zfill(4)}-XX"

        return None

    def _load_dockets_cache(self):
        """Load all dockets into cache for fast lookup."""
        from florida.models import FLDocket

        self._dockets_cache = {}
        dockets = self.db.query(FLDocket).all()

        for d in dockets:
            normalized = self._normalize_docket(d.docket_number)
            if normalized:
                self._dockets_cache[normalized] = {
                    'id': d.id,
                    'docket_number': d.docket_number,
                    'title': d.title,
                }

    def _fuzzy_match_docket(self, normalized: str) -> Optional[Tuple[int, str, float]]:
        """Fuzzy match a docket number against the cache."""
        if not self._dockets_cache or not fuzz:
            return None

        # Use Levenshtein distance on normalized docket numbers
        best_match = None
        best_score = 0

        for cached_norm, cached_data in self._dockets_cache.items():
            score = fuzz.ratio(normalized, cached_norm)
            if score > best_score and score >= THRESHOLDS['docket_fuzzy_review']:
                best_score = score
                best_match = cached_data

        if best_match:
            return (best_match['id'], best_match['docket_number'], best_score)

        return None

    def _calculate_docket_confidence(self, match_score: float, extracted: ExtractedDocket) -> float:
        """Calculate confidence score for a docket match."""
        # Base confidence from match score
        confidence = match_score * 0.7

        # Context boost if docket mentioned in regulatory context
        context_lower = extracted.context.lower()
        if any(term in context_lower for term in ['docket', 'case', 'proceeding', 'hearing']):
            confidence += 15

        # Format validity boost
        if extracted.suffix != "XX":  # Has proper suffix
            confidence += 10

        return min(100, confidence)

    def _match_utilities(self, utilities_data: List[Dict]) -> List[MatchedEntity]:
        """Match extracted utilities against canonical records."""
        from florida.models.linking import FLUtility

        matches = []

        # Load utilities cache
        if self._utilities_cache is None:
            utilities = self.db.query(FLUtility).all()
            self._utilities_cache = []
            for u in utilities:
                names = [u.name, u.normalized_name]
                if u.aliases:
                    names.extend(u.aliases)
                self._utilities_cache.append({
                    'id': u.id,
                    'name': u.name,
                    'normalized_name': u.normalized_name,
                    'all_names': names,
                })

        for util_data in utilities_data:
            name = util_data.get('name', '')
            if not name:
                continue

            role = util_data.get('role', 'subject')
            context = util_data.get('context', '')

            # Try exact match first
            matched = None
            match_type = "none"
            match_score = 0.0

            name_lower = name.lower().strip()

            for cached in self._utilities_cache:
                # Check all name variants
                for variant in cached['all_names']:
                    if variant.lower().strip() == name_lower:
                        matched = cached
                        match_type = "exact"
                        match_score = 100.0
                        break
                if matched:
                    break

            # Try fuzzy match if no exact
            if not matched and fuzz:
                best_score = 0
                for cached in self._utilities_cache:
                    for variant in cached['all_names']:
                        score = fuzz.ratio(name_lower, variant.lower())
                        if score > best_score:
                            best_score = score
                            if score >= THRESHOLDS['utility_fuzzy_review']:
                                matched = cached
                                match_type = "fuzzy"
                                match_score = score

            # Calculate confidence
            if matched:
                if match_type == "exact":
                    confidence = THRESHOLDS['utility_exact']
                else:
                    confidence = match_score * 0.8
                    if role == "applicant":
                        confidence += 10  # Boost for applicant role

                needs_review = confidence < THRESHOLDS['utility_fuzzy_accept']

                matches.append(MatchedEntity(
                    entity_type="utility",
                    extracted_text=name,
                    matched_id=matched['id'],
                    matched_name=matched['name'],
                    match_type=match_type,
                    match_score=match_score,
                    confidence_score=min(100, confidence),
                    needs_review=needs_review,
                    review_reason=f"Fuzzy match ({match_score:.0f}%)" if needs_review else "",
                    context=context[:200] if context else "",
                    role=role
                ))
            else:
                # No match - new utility?
                matches.append(MatchedEntity(
                    entity_type="utility",
                    extracted_text=name,
                    matched_id=None,
                    matched_name=None,
                    match_type="none",
                    match_score=0.0,
                    confidence_score=30.0,
                    needs_review=True,
                    review_reason="No matching utility found",
                    context=context[:200] if context else "",
                    role=role
                ))

        return matches

    def _match_topics(self, topics_data: List[Dict]) -> List[MatchedEntity]:
        """Match extracted topics against canonical records."""
        from florida.models.linking import FLTopic

        matches = []

        # Load topics cache
        if self._topics_cache is None:
            topics = self.db.query(FLTopic).all()
            self._topics_cache = [
                {
                    'id': t.id,
                    'name': t.name,
                    'slug': t.slug,
                    'category': t.category,
                }
                for t in topics
            ]

        for topic_data in topics_data:
            name = topic_data.get('name', '')
            if not name:
                continue

            relevance = topic_data.get('relevance', 'medium')
            sentiment = topic_data.get('sentiment', 'neutral')
            context = topic_data.get('context', '')

            # Try exact match
            matched = None
            match_type = "none"
            match_score = 0.0

            name_lower = name.lower().strip()

            for cached in self._topics_cache:
                if cached['name'].lower() == name_lower or cached['slug'] == name_lower.replace(' ', '-'):
                    matched = cached
                    match_type = "exact"
                    match_score = 100.0
                    break

            # Fuzzy match
            if not matched and fuzz:
                best_score = 0
                for cached in self._topics_cache:
                    score = fuzz.ratio(name_lower, cached['name'].lower())
                    if score > best_score:
                        best_score = score
                        if score >= THRESHOLDS['topic_fuzzy_review']:
                            matched = cached
                            match_type = "fuzzy"
                            match_score = score

            # Calculate confidence
            if matched:
                if match_type == "exact":
                    confidence = THRESHOLDS['topic_exact']
                else:
                    confidence = match_score * 0.85

                if relevance == "high":
                    confidence += 5

                needs_review = confidence < THRESHOLDS['topic_fuzzy_accept']

                matches.append(MatchedEntity(
                    entity_type="topic",
                    extracted_text=name,
                    matched_id=matched['id'],
                    matched_name=matched['name'],
                    match_type=match_type,
                    match_score=match_score,
                    confidence_score=min(100, confidence),
                    needs_review=needs_review,
                    review_reason=f"Fuzzy match ({match_score:.0f}%)" if needs_review else "",
                    context=context[:200] if context else "",
                    relevance=relevance,
                    sentiment=sentiment
                ))
            else:
                # New topic
                matches.append(MatchedEntity(
                    entity_type="topic",
                    extracted_text=name,
                    matched_id=None,
                    matched_name=None,
                    match_type="none",
                    match_score=0.0,
                    confidence_score=40.0,
                    needs_review=True,
                    review_reason="New topic - needs review",
                    context=context[:200] if context else "",
                    relevance=relevance,
                    sentiment=sentiment
                ))

        return matches

    def _save_links(self, hearing_id: int, result: EntityLinkingResult):
        """Save entity links to junction tables."""
        from florida.models.linking import (
            FLHearingDocket, FLHearingUtility, FLHearingTopic, FLUtility, FLTopic
        )

        # Save docket links
        for match in result.dockets:
            if match.matched_id:  # Only save if we have a matched docket
                # Check for existing link
                existing = self.db.query(FLHearingDocket).filter(
                    FLHearingDocket.hearing_id == hearing_id,
                    FLHearingDocket.docket_id == match.matched_id
                ).first()

                if not existing:
                    link = FLHearingDocket(
                        hearing_id=hearing_id,
                        docket_id=match.matched_id,
                        context_summary=match.context,
                        confidence_score=match.confidence_score,
                        match_type=match.match_type,
                        needs_review=match.needs_review,
                        review_reason=match.review_reason,
                        is_primary=(match.confidence_score >= 90),
                    )
                    self.db.add(link)

        # Save utility links
        for match in result.utilities:
            if match.matched_id:
                existing = self.db.query(FLHearingUtility).filter(
                    FLHearingUtility.hearing_id == hearing_id,
                    FLHearingUtility.utility_id == match.matched_id
                ).first()

                if not existing:
                    link = FLHearingUtility(
                        hearing_id=hearing_id,
                        utility_id=match.matched_id,
                        role=match.role,
                        context_summary=match.context,
                        confidence_score=match.confidence_score,
                        match_type=match.match_type,
                        needs_review=match.needs_review,
                        review_reason=match.review_reason,
                    )
                    self.db.add(link)

                    # Update mention count
                    self.db.query(FLUtility).filter(FLUtility.id == match.matched_id).update(
                        {FLUtility.mention_count: FLUtility.mention_count + 1}
                    )

        # Save topic links
        for match in result.topics:
            if match.matched_id:
                existing = self.db.query(FLHearingTopic).filter(
                    FLHearingTopic.hearing_id == hearing_id,
                    FLHearingTopic.topic_id == match.matched_id
                ).first()

                if not existing:
                    # Convert relevance to score
                    relevance_scores = {'high': 0.9, 'medium': 0.6, 'low': 0.3}
                    relevance_score = relevance_scores.get(match.relevance, 0.5)

                    link = FLHearingTopic(
                        hearing_id=hearing_id,
                        topic_id=match.matched_id,
                        relevance_score=relevance_score,
                        sentiment=match.sentiment,
                        context_summary=match.context,
                        confidence_score=match.confidence_score,
                        match_type=match.match_type,
                        needs_review=match.needs_review,
                        review_reason=match.review_reason,
                    )
                    self.db.add(link)

                    # Update mention count
                    self.db.query(FLTopic).filter(FLTopic.id == match.matched_id).update(
                        {FLTopic.mention_count: FLTopic.mention_count + 1}
                    )

        self.db.commit()

    def link_all_hearings(
        self,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        on_progress: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Run entity linking on all hearings that have been analyzed.

        Args:
            status: Only process hearings with this transcript_status (optional)
            limit: Max hearings to process
            on_progress: Progress callback

        Returns:
            Summary statistics
        """
        from florida.models import FLHearing, FLAnalysis
        from florida.models.linking import FLHearingDocket

        # Find hearings that have analysis records (meaning they've been analyzed)
        query = self.db.query(FLHearing).join(
            FLAnalysis, FLAnalysis.hearing_id == FLHearing.id
        )

        if status:
            query = query.filter(FLHearing.transcript_status == status)

        # Exclude hearings that already have links
        linked_hearing_ids = self.db.query(FLHearingDocket.hearing_id).distinct()
        query = query.filter(~FLHearing.id.in_(linked_hearing_ids))

        if limit:
            query = query.limit(limit)

        hearings = query.all()

        stats = {
            'total_processed': 0,
            'total_dockets': 0,
            'total_utilities': 0,
            'total_topics': 0,
            'needs_review': 0,
            'errors': []
        }

        for i, hearing in enumerate(hearings):
            if on_progress:
                on_progress(f"Processing hearing {i+1}/{len(hearings)}: {hearing.title or hearing.id}")

            try:
                result = self.link_hearing(hearing.id)
                stats['total_processed'] += 1
                stats['total_dockets'] += len(result.dockets)
                stats['total_utilities'] += len(result.utilities)
                stats['total_topics'] += len(result.topics)
                stats['needs_review'] += result.needs_review_count
                stats['errors'].extend(result.errors)
            except Exception as e:
                logger.exception(f"Error linking hearing {hearing.id}")
                stats['errors'].append(f"Hearing {hearing.id}: {e}")

        logger.info(
            f"Entity linking complete: {stats['total_processed']} hearings, "
            f"{stats['total_dockets']} dockets, {stats['total_utilities']} utilities, "
            f"{stats['total_topics']} topics"
        )

        return stats


__all__ = ['FloridaEntityLinker', 'EntityLinkingResult', 'MatchedEntity']
