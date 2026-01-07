"""
Smart Entity Validation Pipeline

Unified validation and confidence scoring for all entity types extracted by LLM.
Applies consistent processing: validation → matching → context analysis → confidence scoring.

Entity types:
- Topics: Matched against known topics, validated for category
- Utilities: Matched against known utilities + docket utility names
- Dockets: Matched against known dockets with state-specific format validation

All entities go through the same flow and are assigned:
- confidence: 0-100 score
- status: accepted / needs_review / rejected
- match_type: exact / fuzzy / none
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Try to import rapidfuzz for fuzzy matching
try:
    from rapidfuzz import fuzz, process
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    logger.warning("rapidfuzz not installed - fuzzy matching disabled")

try:
    from slugify import slugify
except ImportError:
    def slugify(text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text)
        return text


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class ValidatedEntity:
    """Base class for validated entities."""
    # Original extraction
    raw_name: str
    normalized_name: str
    context: str = ""

    # Matching
    match_type: str = "none"  # exact, fuzzy, none
    matched_id: Optional[int] = None
    matched_name: Optional[str] = None
    match_score: float = 0.0

    # Confidence scoring
    confidence: int = 0
    status: str = "needs_review"  # accepted, needs_review, rejected
    review_reason: str = ""

    # Flags
    is_new: bool = False  # True if this is a new entity not in known list


@dataclass
class ValidatedTopic(ValidatedEntity):
    """Validated topic with category info."""
    relevance: str = "medium"  # high, medium, low
    sentiment: str = "neutral"
    category: Optional[str] = None  # Matched category if found
    suggested_category: Optional[str] = None


@dataclass
class ValidatedUtility(ValidatedEntity):
    """Validated utility with role info."""
    role: str = "subject"  # applicant, intervenor, subject
    aliases: List[str] = field(default_factory=list)
    utility_type: Optional[str] = None  # IOU, cooperative, municipal
    sector: Optional[str] = None  # Electric, Gas, Water, Telephone
    from_docket_metadata: bool = False  # True if matched via docket utility_name


@dataclass
class ValidatedDocket(ValidatedEntity):
    """Validated docket with format info."""
    state_code: str = ""
    docket_number: str = ""
    format_valid: bool = False
    format_issues: List[str] = field(default_factory=list)
    year: Optional[int] = None
    sector: Optional[str] = None  # Electric, Gas, Water from docket ID parsing
    # Enrichment from known docket metadata
    known_title: Optional[str] = None
    known_utility: Optional[str] = None
    known_utility_type: Optional[str] = None  # Electric, Gas, Water, Telephone
    known_docket_type: Optional[str] = None  # Rate Case, Merger, Certificate, etc.
    known_status: Optional[str] = None  # open, closed, pending
    known_filing_date: Optional[str] = None
    # Context validation results
    utility_context_match: bool = False  # True if docket utility matches hearing utility mentions
    type_context_match: bool = False  # True if docket_type matches hearing context


# =============================================================================
# Context Scoring Rules (shared across entity types)
# =============================================================================

# Regulatory context boosters
REGULATORY_CONTEXT = [
    (r'\b(commission|puc|puct|psc|cpuc|fpsc|gpsc)\b', 10, "regulatory body"),
    (r'\b(hearing|testimony|witness|docket|case)\b', 8, "proceeding language"),
    (r'\b(rate\s*case|rate\s*increase|tariff|filing)\b', 12, "rate case"),
    (r'\b(application|petition|complaint|order)\b', 8, "filing type"),
]

# Topic-specific context
TOPIC_CONTEXT = [
    (r'\b(renewable|solar|wind|battery|storage)\b', 15, "clean energy"),
    (r'\b(rate|pricing|cost|charge|fee|tariff)\b', 12, "rate-related"),
    (r'\b(reliability|outage|resilience|grid)\b', 12, "reliability"),
    (r'\b(customer|consumer|ratepayer|residential)\b', 10, "consumer"),
    (r'\b(environmental|emissions|carbon|climate)\b', 12, "environmental"),
]

# Utility-specific context
UTILITY_CONTEXT = [
    (r'\b(applicant|petitioner|respondent)\b', 15, "party role"),
    (r'\b(utility|company|corporation|inc|llc)\b', 8, "company term"),
    (r'\b(electric|gas|water|telecom|power)\b', 10, "sector"),
    (r'\b(service|territory|customers|rates)\b', 8, "utility terms"),
]


# =============================================================================
# Base Validator
# =============================================================================

class EntityValidator(ABC):
    """Base class for entity validators."""

    # Confidence thresholds
    ACCEPT_THRESHOLD = 85
    REVIEW_THRESHOLD = 50

    def __init__(self, db: Session):
        self.db = db
        self._cache: Dict[str, Any] = {}

    @abstractmethod
    def validate(self, entity_data: Dict[str, Any], hearing_context: Dict[str, Any]) -> ValidatedEntity:
        """Validate a single extracted entity."""
        pass

    def _calculate_context_score(self, context: str, patterns: List[Tuple]) -> Tuple[int, List[str]]:
        """Calculate context score based on pattern matches."""
        score = 0
        clues = []
        context_lower = context.lower()

        for pattern, points, name in patterns:
            if re.search(pattern, context_lower, re.IGNORECASE):
                score += points
                clues.append(name)

        return min(score, 50), clues  # Cap at 50

    def _fuzzy_match(self, name: str, known_names: List[str], threshold: int = 80) -> Optional[Tuple[str, float]]:
        """Find best fuzzy match for a name."""
        if not FUZZY_AVAILABLE or not known_names:
            return None

        result = process.extractOne(
            name.lower(),
            [n.lower() for n in known_names],
            scorer=fuzz.ratio,
            score_cutoff=threshold
        )

        if result:
            matched_lower, score, _ = result
            # Find original case version
            for known in known_names:
                if known.lower() == matched_lower:
                    return known, score / 100.0

        return None


# =============================================================================
# Topic Validator
# =============================================================================

class TopicValidator(EntityValidator):
    """Validates topics against known topic database."""

    # Known topic categories and their keywords
    TOPIC_KEYWORDS = {
        "rate_design": ["rate", "pricing", "tariff", "cost", "charge", "fee", "billing"],
        "renewable_energy": ["solar", "wind", "renewable", "clean energy", "green"],
        "grid_reliability": ["reliability", "outage", "resilience", "grid", "infrastructure"],
        "battery_storage": ["battery", "storage", "energy storage"],
        "electric_vehicles": ["ev", "electric vehicle", "charging", "evse"],
        "natural_gas": ["gas", "natural gas", "lng", "pipeline"],
        "consumer_protection": ["consumer", "customer", "ratepayer", "low income", "affordability"],
        "environmental": ["environmental", "emissions", "carbon", "climate", "pollution"],
        "transmission": ["transmission", "interconnection", "grid connection"],
        "efficiency": ["efficiency", "conservation", "demand response", "demand side"],
    }

    def __init__(self, db: Session):
        super().__init__(db)
        self._load_known_topics()

    def _load_known_topics(self):
        """Load known topics into cache."""
        from app.models.database import Topic

        topics = self.db.query(Topic).all()
        self._cache = {
            'by_slug': {t.slug: t for t in topics},
            'by_name': {t.name.lower(): t for t in topics},
            'names': [t.name for t in topics],
            'categorized': {t.name: t.category for t in topics if t.category != 'uncategorized'},
        }

    def validate(self, entity_data: Dict[str, Any], hearing_context: Dict[str, Any]) -> ValidatedTopic:
        """Validate a topic extraction."""
        name = entity_data.get('name', '').strip()
        context = entity_data.get('context', '')
        relevance = entity_data.get('relevance', 'medium')
        sentiment = entity_data.get('sentiment', 'neutral')

        slug = slugify(name)

        result = ValidatedTopic(
            raw_name=name,
            normalized_name=slug,
            context=context,
            relevance=relevance,
            sentiment=sentiment,
        )

        # Check for exact match
        if slug in self._cache['by_slug']:
            known = self._cache['by_slug'][slug]
            result.match_type = "exact"
            result.matched_id = known.id
            result.matched_name = known.name
            result.match_score = 1.0
            result.category = known.category
            result.is_new = False
        elif name.lower() in self._cache['by_name']:
            known = self._cache['by_name'][name.lower()]
            result.match_type = "exact"
            result.matched_id = known.id
            result.matched_name = known.name
            result.match_score = 1.0
            result.category = known.category
            result.is_new = False
        else:
            # Try fuzzy match
            match = self._fuzzy_match(name, self._cache['names'], threshold=85)
            if match:
                matched_name, score = match
                if matched_name.lower() in self._cache['by_name']:
                    known = self._cache['by_name'][matched_name.lower()]
                    result.match_type = "fuzzy"
                    result.matched_id = known.id
                    result.matched_name = known.name
                    result.match_score = score
                    result.category = known.category
                    result.is_new = False
            else:
                result.is_new = True
                # Suggest category based on keywords
                result.suggested_category = self._suggest_category(name, context)

        # Context scoring
        all_context = f"{context} {hearing_context.get('title', '')} {hearing_context.get('summary', '')}"
        ctx_score, clues = self._calculate_context_score(all_context, TOPIC_CONTEXT + REGULATORY_CONTEXT)

        # Calculate confidence
        result.confidence = self._calculate_confidence(result, ctx_score)
        result.status = self._determine_status(result)
        result.review_reason = self._build_review_reason(result)

        return result

    def _suggest_category(self, name: str, context: str) -> Optional[str]:
        """Suggest a category based on keywords."""
        text = f"{name} {context}".lower()

        for category, keywords in self.TOPIC_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                return category

        return "uncategorized"

    def _calculate_confidence(self, result: ValidatedTopic, ctx_score: int) -> int:
        """Calculate confidence score for topic."""
        base_score = 0

        if result.match_type == "exact":
            base_score = 90
        elif result.match_type == "fuzzy":
            base_score = int(70 + (result.match_score * 20))
        else:
            # New topic - base on context quality
            base_score = 40 + ctx_score

        # Boost for categorized topics
        if result.category and result.category != "uncategorized":
            base_score = min(100, base_score + 10)

        return min(100, base_score)

    def _determine_status(self, result: ValidatedTopic) -> str:
        """Determine review status."""
        # All new topics need review
        if result.is_new:
            return "needs_review"

        # Uncategorized topics need review
        if result.category == "uncategorized":
            return "needs_review"

        if result.confidence >= self.ACCEPT_THRESHOLD:
            return "accepted"
        elif result.confidence >= self.REVIEW_THRESHOLD:
            return "needs_review"
        else:
            return "rejected"

    def _build_review_reason(self, result: ValidatedTopic) -> str:
        """Build review reason."""
        reasons = []

        if result.is_new:
            reasons.append("New topic")

        if result.match_type == "fuzzy":
            reasons.append(f"Fuzzy match ({result.match_score:.0%})")

        if result.category == "uncategorized" or not result.category:
            reasons.append("Needs categorization")

        return "; ".join(reasons) if reasons else ""


# =============================================================================
# Utility Validator
# =============================================================================

class UtilityValidator(EntityValidator):
    """Validates utilities against known utility database and docket data."""

    def __init__(self, db: Session):
        super().__init__(db)
        self._load_known_utilities()

    def _load_known_utilities(self):
        """Load known utilities into cache, including from docket metadata."""
        from app.models.database import Utility, KnownDocket

        # Load from utilities table
        utilities = self.db.query(Utility).all()
        utility_names = {}
        for u in utilities:
            utility_names[u.name.lower()] = {'entity': u, 'source': 'utility'}
            utility_names[u.normalized_name] = {'entity': u, 'source': 'utility'}
            for alias in (u.aliases or []):
                utility_names[alias.lower()] = {'entity': u, 'source': 'utility'}

        # Load utility names + metadata from known dockets
        docket_utilities = self.db.query(
            KnownDocket.utility_name,
            KnownDocket.utility_type,
            KnownDocket.state_code
        ).filter(
            KnownDocket.utility_name.isnot(None)
        ).distinct().all()

        known_utility_names = set(u.name for u in utilities)
        utility_metadata = {}  # utility_name -> {utility_type, states}

        for name, utility_type, state_code in docket_utilities:
            if name and name.strip():
                clean_name = name.strip()
                known_utility_names.add(clean_name)

                # Track metadata
                if clean_name not in utility_metadata:
                    utility_metadata[clean_name] = {
                        'utility_type': utility_type,
                        'states': set(),
                    }
                if state_code:
                    utility_metadata[clean_name]['states'].add(state_code)
                # Update utility_type if we get a more specific one
                if utility_type and not utility_metadata[clean_name]['utility_type']:
                    utility_metadata[clean_name]['utility_type'] = utility_type

        self._cache = {
            'by_name': utility_names,
            'names': list(known_utility_names),
            'utilities': {u.id: u for u in utilities},
            'docket_metadata': utility_metadata,  # Metadata from known dockets
        }

    def validate(self, entity_data: Dict[str, Any], hearing_context: Dict[str, Any]) -> ValidatedUtility:
        """Validate a utility extraction."""
        name = entity_data.get('name', '').strip()
        context = entity_data.get('context', '')
        role = entity_data.get('role', 'subject')
        aliases = entity_data.get('aliases', [])
        state_code = hearing_context.get('state_code', '')

        normalized = slugify(name)

        result = ValidatedUtility(
            raw_name=name,
            normalized_name=normalized,
            context=context,
            role=role,
            aliases=aliases,
        )

        # Check for exact match in utilities table
        if name.lower() in self._cache['by_name']:
            cached = self._cache['by_name'][name.lower()]
            known = cached['entity']
            result.match_type = "exact"
            result.matched_id = known.id
            result.matched_name = known.name
            result.match_score = 1.0
            result.utility_type = known.utility_type
            result.is_new = False
        elif normalized in self._cache['by_name']:
            cached = self._cache['by_name'][normalized]
            known = cached['entity']
            result.match_type = "exact"
            result.matched_id = known.id
            result.matched_name = known.name
            result.match_score = 1.0
            result.utility_type = known.utility_type
            result.is_new = False
        else:
            # Check aliases
            for alias in aliases:
                if alias.lower() in self._cache['by_name']:
                    cached = self._cache['by_name'][alias.lower()]
                    known = cached['entity']
                    result.match_type = "exact"
                    result.matched_id = known.id
                    result.matched_name = known.name
                    result.match_score = 1.0
                    result.is_new = False
                    break

            if result.match_type == "none":
                # Try fuzzy match against all known names (utilities + docket metadata)
                match = self._fuzzy_match(name, self._cache['names'], threshold=80)
                if match:
                    matched_name, score = match
                    result.match_type = "fuzzy"
                    result.matched_name = matched_name
                    result.match_score = score
                    result.is_new = False

                    # Try to get ID and type from utilities table
                    if matched_name.lower() in self._cache['by_name']:
                        cached = self._cache['by_name'][matched_name.lower()]
                        known = cached['entity']
                        result.matched_id = known.id
                        result.utility_type = known.utility_type
                    # Otherwise try docket metadata
                    elif matched_name in self._cache['docket_metadata']:
                        meta = self._cache['docket_metadata'][matched_name]
                        result.sector = meta.get('utility_type')
                        result.from_docket_metadata = True
                else:
                    result.is_new = True

        # Enrich with docket metadata if we have a match
        if result.matched_name and result.matched_name in self._cache['docket_metadata']:
            meta = self._cache['docket_metadata'][result.matched_name]
            if not result.sector:
                result.sector = meta.get('utility_type')
            result.from_docket_metadata = True

            # Validate against state - boost confidence if utility operates in this state
            if state_code and state_code in meta.get('states', set()):
                result.match_score = min(1.0, result.match_score + 0.1)

        # Context scoring
        all_context = f"{context} {hearing_context.get('title', '')} {hearing_context.get('summary', '')}"
        ctx_score, clues = self._calculate_context_score(all_context, UTILITY_CONTEXT + REGULATORY_CONTEXT)

        # Calculate confidence
        result.confidence = self._calculate_confidence(result, ctx_score)
        result.status = self._determine_status(result)
        result.review_reason = self._build_review_reason(result)

        return result

    def _calculate_confidence(self, result: ValidatedUtility, ctx_score: int) -> int:
        """Calculate confidence score for utility."""
        base_score = 0

        if result.match_type == "exact":
            base_score = 95
        elif result.match_type == "fuzzy":
            base_score = int(65 + (result.match_score * 25))
        else:
            # New utility - base on context
            base_score = 35 + ctx_score

        # Boost for applicant role (more likely to be correctly identified)
        if result.role == "applicant":
            base_score = min(100, base_score + 5)

        return min(100, base_score)

    def _determine_status(self, result: ValidatedUtility) -> str:
        """Determine review status."""
        # All entities need review per user requirement
        return "needs_review"

    def _build_review_reason(self, result: ValidatedUtility) -> str:
        """Build review reason."""
        reasons = []

        if result.is_new:
            reasons.append("New utility")

        if result.match_type == "fuzzy":
            reasons.append(f"Fuzzy match ({result.match_score:.0%})")
        elif result.match_type == "none":
            reasons.append("No known match")

        return "; ".join(reasons) if reasons else "Pending verification"


# =============================================================================
# Docket Validator
# =============================================================================

class DocketValidator(EntityValidator):
    """Validates dockets against known docket database."""

    # State-specific format patterns
    STATE_FORMATS = {
        "FL": r'^\d{8}-[A-Z]{2}$',
        "TX": r'^\d{5}$',
        "GA": r'^\d{5}$',
        "CA": r'^[ARCIP]\.\d{2}-\d{2}-\d{3}$',
        "OH": r'^\d{2}-\d{4}-[A-Z]{2}-[A-Z]{2,3}$',
    }

    def __init__(self, db: Session):
        super().__init__(db)
        self._known_dockets_cache: Dict[str, Dict] = {}

    def _load_known_dockets(self, state_code: str):
        """Load known dockets for a state into cache with full metadata."""
        if state_code in self._known_dockets_cache:
            return

        from app.models.database import KnownDocket
        from app.services.docket_parser import normalize_for_matching

        known = self.db.query(KnownDocket).filter(
            KnownDocket.state_code == state_code
        ).all()

        # Build lookup indexes
        by_normalized = {}
        by_title = {}  # For title-based fuzzy matching
        by_utility = {}  # For utility-based lookup

        for d in known:
            norm_id = normalize_for_matching(d.normalized_id)
            by_normalized[norm_id] = d

            # Index by title words for fuzzy matching
            if d.title:
                title_key = d.title.lower()[:100]  # First 100 chars
                by_title[title_key] = d

            # Index by utility name
            if d.utility_name:
                util_key = d.utility_name.lower()
                if util_key not in by_utility:
                    by_utility[util_key] = []
                by_utility[util_key].append(d)

        self._known_dockets_cache[state_code] = {
            'by_normalized': by_normalized,
            'by_title': by_title,
            'by_utility': by_utility,
            'titles': [d.title for d in known if d.title],  # For fuzzy matching
            'dockets': known,
        }

    def validate(self, entity_data: Dict[str, Any], hearing_context: Dict[str, Any]) -> ValidatedDocket:
        """Validate a docket extraction."""
        from app.services.docket_parser import parse_docket, normalize_for_matching

        number = entity_data.get('number', '').strip()
        context = entity_data.get('context', '')
        state_code = hearing_context.get('state_code', 'XX')

        # Parse the docket number
        try:
            parsed = parse_docket(number, state_code)
            normalized_id = parsed.normalized_id
        except Exception:
            normalized_id = f"{state_code}-{number}"

        result = ValidatedDocket(
            raw_name=number,
            normalized_name=normalized_id,
            context=context,
            state_code=state_code,
            docket_number=number,
        )

        # Format validation
        result.format_valid, result.format_issues = self._validate_format(number, state_code)

        # Try to extract year/sector from parsed data
        try:
            parsed = parse_docket(number, state_code)
            result.year = parsed.year
            result.sector = parsed.utility_sector
        except Exception:
            pass

        # Load known dockets for this state
        self._load_known_dockets(state_code)

        # Match against known dockets
        self._match_known_docket(result, state_code, hearing_context)

        # Validate docket_type matches hearing context
        all_context = f"{context} {hearing_context.get('title', '')} {hearing_context.get('summary', '')}".lower()
        result.type_context_match = self._validate_docket_type_context(result, all_context)

        # Context scoring
        ctx_score, clues = self._calculate_context_score(all_context, REGULATORY_CONTEXT)

        # Boost score if docket_type matches context
        if result.type_context_match:
            ctx_score = min(50, ctx_score + 15)

        # Calculate confidence
        result.confidence = self._calculate_confidence(result, ctx_score)
        result.status = self._determine_status(result)
        result.review_reason = self._build_review_reason(result)

        return result

    def _validate_docket_type_context(self, result: ValidatedDocket, context: str) -> bool:
        """Check if docket_type matches the hearing context."""
        if not result.known_docket_type:
            return False

        docket_type = result.known_docket_type.lower()

        # Map docket types to context keywords
        type_keywords = {
            'rate case': ['rate case', 'rate increase', 'rate decrease', 'rate adjustment', 'general rate', 'base rate'],
            'merger': ['merger', 'acquisition', 'combination', 'purchase'],
            'certificate': ['certificate', 'authorization', 'franchise', 'cpcn'],
            'complaint': ['complaint', 'dispute', 'violation'],
            'rulemaking': ['rulemaking', 'rule', 'regulation', 'policy'],
            'investigation': ['investigation', 'inquiry', 'audit', 'review'],
            'application': ['application', 'petition', 'request', 'approval'],
        }

        for dt, keywords in type_keywords.items():
            if dt in docket_type:
                if any(kw in context for kw in keywords):
                    return True

        return False

    def _validate_format(self, docket_number: str, state_code: str) -> Tuple[bool, List[str]]:
        """Validate docket format against state-specific rules."""
        issues = []

        if state_code in self.STATE_FORMATS:
            pattern = self.STATE_FORMATS[state_code]
            # Clean the docket number
            cleaned = re.sub(r'^(Docket|Case|Project)\s*(No\.?\s*)?', '', docket_number, flags=re.I).strip()
            if not re.match(pattern, cleaned):
                issues.append(f"Format doesn't match {state_code} pattern")

        return len(issues) == 0, issues

    def _match_known_docket(self, result: ValidatedDocket, state_code: str, hearing_context: Dict[str, Any]):
        """Match against known dockets using ID, title, and utility."""
        from app.services.docket_parser import normalize_for_matching

        cache = self._known_dockets_cache.get(state_code, {})
        by_normalized = cache.get('by_normalized', {})

        if not by_normalized:
            result.is_new = True
            return

        normalized = normalize_for_matching(result.normalized_name)

        # Exact match by docket ID
        if normalized in by_normalized:
            known = by_normalized[normalized]
            self._enrich_from_known(result, known, "exact", 1.0)
            return

        # Fuzzy match by docket ID
        if FUZZY_AVAILABLE:
            matches = process.extractOne(
                normalized,
                list(by_normalized.keys()),
                scorer=fuzz.ratio,
                score_cutoff=70
            )

            if matches:
                matched_key, score, _ = matches
                known = by_normalized[matched_key]
                self._enrich_from_known(result, known, "fuzzy", score / 100.0)
                return

        # If no ID match, try title-based fuzzy matching (for malformed docket numbers)
        titles = cache.get('titles', [])
        if FUZZY_AVAILABLE and titles and result.context:
            # Look for title matches in the hearing context
            hearing_text = f"{hearing_context.get('title', '')} {hearing_context.get('summary', '')}"
            title_match = process.extractOne(
                hearing_text[:200],
                titles,
                scorer=fuzz.partial_ratio,
                score_cutoff=60
            )

            if title_match:
                matched_title, score, _ = title_match
                by_title = cache.get('by_title', {})
                for title_key, docket in by_title.items():
                    if docket.title == matched_title:
                        self._enrich_from_known(result, docket, "fuzzy", score / 100.0)
                        result.review_reason = f"Matched by title similarity ({score}%)"
                        return

        result.is_new = True

    def _enrich_from_known(self, result: ValidatedDocket, known, match_type: str, score: float):
        """Enrich result with all metadata from known docket."""
        result.match_type = match_type
        result.matched_id = known.id
        result.matched_name = known.docket_number
        result.match_score = score
        result.is_new = False

        # Core metadata
        result.known_title = known.title
        result.known_utility = known.utility_name

        # Extended metadata from scraped docket data
        result.known_utility_type = getattr(known, 'utility_type', None)
        result.known_docket_type = getattr(known, 'docket_type', None)
        result.known_status = getattr(known, 'status', None)
        if hasattr(known, 'filing_date') and known.filing_date:
            result.known_filing_date = str(known.filing_date)

    def _calculate_confidence(self, result: ValidatedDocket, ctx_score: int) -> int:
        """Calculate confidence score for docket."""
        base_score = 0

        if result.match_type == "exact":
            base_score = 95
        elif result.match_type == "fuzzy":
            base_score = int(60 + (result.match_score * 30))
        else:
            # Unmatched docket
            if result.format_valid:
                base_score = 40 + ctx_score
            else:
                base_score = 20 + ctx_score

        # Penalty for format issues
        if result.format_issues:
            base_score = max(10, base_score - 15)

        return min(100, base_score)

    def _determine_status(self, result: ValidatedDocket) -> str:
        """Determine review status - all dockets need review."""
        return "needs_review"

    def _build_review_reason(self, result: ValidatedDocket) -> str:
        """Build review reason."""
        reasons = []

        if result.is_new:
            reasons.append("Not in known dockets")

        if result.match_type == "fuzzy":
            reasons.append(f"Fuzzy match ({result.match_score:.0%})")

        if result.format_issues:
            reasons.append(f"Format: {', '.join(result.format_issues)}")

        return "; ".join(reasons) if reasons else "Pending verification"


# =============================================================================
# Unified Validation Pipeline
# =============================================================================

class EntityValidationPipeline:
    """
    Unified pipeline for validating all entity types from LLM extraction.
    """

    def __init__(self, db: Session):
        self.db = db
        self.topic_validator = TopicValidator(db)
        self.utility_validator = UtilityValidator(db)
        self.docket_validator = DocketValidator(db)

    def validate_all(
        self,
        topics_extracted: List[Dict],
        utilities_extracted: List[Dict],
        dockets_extracted: List[Dict],
        hearing_context: Dict[str, Any]
    ) -> Dict[str, List]:
        """
        Validate all extracted entities.

        Args:
            topics_extracted: List of topic dicts from LLM
            utilities_extracted: List of utility dicts from LLM
            dockets_extracted: List of docket dicts from LLM
            hearing_context: Context about the hearing (title, summary, state_code, etc.)

        Returns:
            Dict with validated entities:
            {
                'topics': [ValidatedTopic, ...],
                'utilities': [ValidatedUtility, ...],
                'dockets': [ValidatedDocket, ...],
            }
        """
        results = {
            'topics': [],
            'utilities': [],
            'dockets': [],
        }

        # Validate topics
        for topic_data in (topics_extracted or []):
            try:
                validated = self.topic_validator.validate(topic_data, hearing_context)
                results['topics'].append(validated)
            except Exception as e:
                logger.warning(f"Failed to validate topic {topic_data}: {e}")

        # Validate utilities
        for utility_data in (utilities_extracted or []):
            try:
                validated = self.utility_validator.validate(utility_data, hearing_context)
                results['utilities'].append(validated)
            except Exception as e:
                logger.warning(f"Failed to validate utility {utility_data}: {e}")

        # Validate dockets
        for docket_data in (dockets_extracted or []):
            try:
                validated = self.docket_validator.validate(docket_data, hearing_context)
                results['dockets'].append(validated)
            except Exception as e:
                logger.warning(f"Failed to validate docket {docket_data}: {e}")

        # Cross-entity validation: check utility-docket relationships
        self._cross_validate_utilities_and_dockets(results)

        # Log summary
        logger.info(
            f"Validated entities: "
            f"{len(results['topics'])} topics, "
            f"{len(results['utilities'])} utilities, "
            f"{len(results['dockets'])} dockets"
        )

        return results

    def _cross_validate_utilities_and_dockets(self, results: Dict[str, List]):
        """
        Cross-validate utilities against dockets.
        If a docket's utility_name matches an extracted utility, boost confidence.
        If there's a mismatch, flag for review.
        """
        utilities = results.get('utilities', [])
        dockets = results.get('dockets', [])

        if not utilities or not dockets:
            return

        # Build set of utility names (normalized) from extractions
        utility_names = set()
        utility_lookup = {}
        for u in utilities:
            if u.raw_name:
                utility_names.add(u.raw_name.lower())
                utility_lookup[u.raw_name.lower()] = u
            if u.matched_name:
                utility_names.add(u.matched_name.lower())
                utility_lookup[u.matched_name.lower()] = u
            for alias in u.aliases:
                utility_names.add(alias.lower())
                utility_lookup[alias.lower()] = u

        # Check each docket
        for docket in dockets:
            if not docket.known_utility:
                continue

            docket_utility = docket.known_utility.lower()

            # Check for exact match
            if docket_utility in utility_names:
                docket.utility_context_match = True
                # Boost docket confidence
                docket.confidence = min(100, docket.confidence + 10)

                # Also boost the matching utility
                if docket_utility in utility_lookup:
                    utility = utility_lookup[docket_utility]
                    utility.confidence = min(100, utility.confidence + 5)
                    if not utility.review_reason:
                        utility.review_reason = "Confirmed by docket reference"

                logger.debug(f"Cross-validation: docket {docket.docket_number} utility '{docket.known_utility}' matches extraction")

            elif FUZZY_AVAILABLE:
                # Try fuzzy match
                from rapidfuzz import fuzz, process
                match = process.extractOne(
                    docket_utility,
                    list(utility_names),
                    scorer=fuzz.ratio,
                    score_cutoff=80
                )

                if match:
                    matched_name, score, _ = match
                    docket.utility_context_match = True
                    docket.confidence = min(100, docket.confidence + 5)

                    if matched_name in utility_lookup:
                        utility = utility_lookup[matched_name]
                        utility.confidence = min(100, utility.confidence + 3)

                    logger.debug(f"Cross-validation: fuzzy match {docket.known_utility} ~ {matched_name} ({score}%)")
                else:
                    # Utility mismatch - flag for review
                    if docket.review_reason:
                        docket.review_reason += f"; Utility mismatch: docket has '{docket.known_utility}'"
                    else:
                        docket.review_reason = f"Utility mismatch: docket has '{docket.known_utility}'"
