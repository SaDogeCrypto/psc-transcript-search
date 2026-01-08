# Smart Docket Extraction Pipeline

## Problem Statement

Current extraction is "dumb regex":
- Finds anything matching a pattern
- Stores it without validation
- No confidence scoring
- No cross-referencing
- Transcription errors propagate unchecked

Example failure:
- Transcript: "project number 5599" (STT error)
- Actual: Project No. 55999 (ERCOT Reports)
- System stored TX-5599 with no flags

## Design Goals

1. **Extract candidates, not matches** - Everything starts as a candidate
2. **Validate against multiple sources** - Format rules, known dockets, context
3. **Score confidence** - 0-100 based on evidence
4. **Flag uncertain extractions** - Human review for low confidence
5. **Learn from corrections** - Improve over time

---

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         TRANSCRIPT TEXT                              │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 1: CANDIDATE EXTRACTION                                       │
│  ─────────────────────────────────────────────────────────────────  │
│  • Regex patterns (state-specific + generic)                        │
│  • Context window capture (50 chars before/after)                   │
│  • Trigger phrase detection ("docket", "project", "case")           │
│                                                                      │
│  Output: List of CandidateDocket objects                            │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 2: FORMAT VALIDATION                                          │
│  ─────────────────────────────────────────────────────────────────  │
│  • Check against state-specific format rules                        │
│  • Validate digit counts, prefixes, separators                      │
│  • Flag format violations (e.g., 4-digit TX number)                 │
│                                                                      │
│  Output: format_valid (bool), format_score (0-100)                  │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 3: KNOWN DOCKET MATCHING                                      │
│  ─────────────────────────────────────────────────────────────────  │
│  • Exact match against known_dockets table                          │
│  • Fuzzy match for near-misses (Levenshtein distance ≤ 2)          │
│  • Number transposition detection (5599 ↔ 55999)                    │
│                                                                      │
│  Output: match_type (exact|fuzzy|none), matched_docket_id,          │
│          fuzzy_score, suggested_correction                          │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 4: CONTEXT ANALYSIS                                           │
│  ─────────────────────────────────────────────────────────────────  │
│  • Score based on trigger phrases                                   │
│    - "docket number X" = +30                                        │
│    - "project number X" = +30                                       │
│    - "case X" = +20                                                 │
│    - "item number X" = +10                                          │
│    - Bare number in text = +0                                       │
│  • Entity co-occurrence (utility name nearby = +20)                 │
│  • Semantic context (discussing rates, filings, etc.)               │
│                                                                      │
│  Output: context_score (0-100), context_clues[]                     │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 5: CONFIDENCE SCORING                                         │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  confidence = weighted_average(                                      │
│      format_score      × 0.25,                                      │
│      match_score       × 0.40,   # Highest weight - known docket    │
│      context_score     × 0.25,                                      │
│      fuzzy_bonus       × 0.10,   # Bonus if fuzzy match found       │
│  )                                                                   │
│                                                                      │
│  Thresholds:                                                         │
│  • confidence >= 80: AUTO_ACCEPT                                    │
│  • confidence 50-79: NEEDS_REVIEW                                   │
│  • confidence < 50:  AUTO_REJECT (or flag for review)               │
│                                                                      │
│  Output: final_confidence, status, review_reason                    │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 6: CORRECTION SUGGESTIONS                                     │
│  ─────────────────────────────────────────────────────────────────  │
│  If fuzzy match found but not exact:                                │
│  • Suggest correction: "5599 → 55999?"                              │
│  • Show evidence: "Known docket 55999 = ERCOT Reports"              │
│  • Show context match: "transcript mentions ERCOT"                  │
│                                                                      │
│  Output: suggested_docket, correction_confidence, evidence[]        │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│  STAGE 7: STORAGE & REVIEW QUEUE                                     │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                      │
│  Store in extracted_dockets table:                                  │
│  • hearing_id, raw_text, normalized_id                              │
│  • confidence_score, status (accepted|review|rejected)              │
│  • format_valid, match_type, matched_known_docket_id                │
│  • suggested_correction, correction_confidence                      │
│  • context_window, trigger_phrase                                   │
│  • reviewed_by, reviewed_at, final_docket_id                        │
│                                                                      │
│  If NEEDS_REVIEW: Add to review queue with:                         │
│  • Original extraction + context                                    │
│  • Suggested correction (if any)                                    │
│  • Evidence for/against                                             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Model

### CandidateDocket (intermediate object)

```python
@dataclass
class CandidateDocket:
    # Extraction
    raw_text: str              # "5599" as found in transcript
    normalized: str            # "TX-5599"
    context_before: str        # "item number nine. That's project number"
    context_after: str         # "Reports of the Electric Reliability"
    trigger_phrase: str        # "project number"
    position: int              # Character offset in transcript

    # Validation scores
    format_valid: bool
    format_score: int          # 0-100

    # Known docket matching
    match_type: str            # "exact", "fuzzy", "none"
    matched_docket_id: int     # FK to known_dockets
    fuzzy_score: int           # 0-100 (100 = exact)
    fuzzy_candidates: List     # Near-misses

    # Context analysis
    context_score: int         # 0-100
    context_clues: List[str]   # ["mentions ERCOT", "discusses reports"]

    # Final scoring
    confidence: int            # 0-100
    status: str                # "accepted", "needs_review", "rejected"
    review_reason: str         # Why flagged for review

    # Correction suggestion
    suggested_correction: str  # "55999"
    correction_confidence: int # How confident in suggestion
    correction_evidence: List  # Why we suggest this
```

### ExtractedDocket (database table)

```sql
CREATE TABLE extracted_dockets (
    id INTEGER PRIMARY KEY,
    hearing_id INTEGER NOT NULL,

    -- What was extracted
    raw_text VARCHAR(100),
    normalized_id VARCHAR(60),
    context_window TEXT,
    trigger_phrase VARCHAR(50),
    transcript_position INTEGER,

    -- Validation results
    format_valid BOOLEAN,
    format_score INTEGER,
    match_type VARCHAR(20),  -- exact, fuzzy, none
    matched_known_docket_id INTEGER,
    fuzzy_score INTEGER,

    -- Scoring
    context_score INTEGER,
    confidence_score INTEGER,
    status VARCHAR(20),  -- accepted, needs_review, rejected
    review_reason TEXT,

    -- Correction suggestion
    suggested_docket_id INTEGER,
    suggested_correction VARCHAR(60),
    correction_confidence INTEGER,
    correction_evidence TEXT,  -- JSON

    -- Review tracking
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP,
    review_decision VARCHAR(20),  -- confirmed, corrected, rejected
    final_docket_id INTEGER,  -- After review, what docket was confirmed

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (hearing_id) REFERENCES hearings(id),
    FOREIGN KEY (matched_known_docket_id) REFERENCES known_dockets(id),
    FOREIGN KEY (suggested_docket_id) REFERENCES known_dockets(id),
    FOREIGN KEY (final_docket_id) REFERENCES known_dockets(id)
);

CREATE INDEX idx_extracted_status ON extracted_dockets(status);
CREATE INDEX idx_extracted_hearing ON extracted_dockets(hearing_id);
CREATE INDEX idx_extracted_confidence ON extracted_dockets(confidence_score);
```

---

## State Format Rules

```python
STATE_DOCKET_RULES = {
    "TX": {
        "patterns": [
            r'\b(\d{5})\b',  # 5-digit docket/project numbers
        ],
        "validators": [
            lambda x: len(x) == 5,  # Must be exactly 5 digits
            lambda x: 30000 <= int(x) <= 99999,  # Reasonable range
        ],
        "format_description": "5-digit number (e.g., 55999)",
    },
    "FL": {
        "patterns": [
            r'\b(\d{8}-[A-Z]{2})\b',  # YYYYNNNN-XX
        ],
        "validators": [
            lambda x: re.match(r'^\d{8}-[A-Z]{2}$', x),
            lambda x: 2000 <= int(x[:4]) <= 2030,  # Year range
        ],
        "format_description": "YYYYNNNN-XX (e.g., 20250035-GU)",
    },
    "CA": {
        "patterns": [
            r'\b([ARCIP]\.\d{2}-\d{2}-\d{3})\b',
        ],
        "validators": [
            lambda x: re.match(r'^[ARCIP]\.\d{2}-\d{2}-\d{3}$', x),
            lambda x: 1 <= int(x.split('-')[1]) <= 12,  # Valid month
        ],
        "format_description": "X.YY-MM-NNN (e.g., A.25-07-003)",
    },
    "GA": {
        "patterns": [
            r'\b(\d{5})\b',
        ],
        "validators": [
            lambda x: len(x) == 5,
            lambda x: 40000 <= int(x) <= 50000,  # Current range
        ],
        "format_description": "5-digit number (e.g., 44280)",
    },
    "OH": {
        "patterns": [
            r'\b(\d{2}-\d{4}-[A-Z]{2}-[A-Z]{2,3})\b',
        ],
        "validators": [
            lambda x: re.match(r'^\d{2}-\d{4}-[A-Z]{2}-[A-Z]{2,3}$', x),
        ],
        "format_description": "YY-NNNN-XX-XXX (e.g., 25-0594-EL-AIR)",
    },
}
```

---

## Fuzzy Matching Strategy

For near-miss detection:

```python
def find_fuzzy_matches(extracted: str, state_code: str, known_dockets: List) -> List[FuzzyMatch]:
    """Find near-matches in known dockets."""
    matches = []

    for known in known_dockets:
        # Skip if different state
        if known.state_code != state_code:
            continue

        # Calculate similarity
        distance = levenshtein_distance(extracted, known.docket_number)

        # Check for common transcription errors
        is_digit_drop = is_missing_digit(extracted, known.docket_number)
        is_transposition = is_digit_transposition(extracted, known.docket_number)

        if distance <= 2 or is_digit_drop or is_transposition:
            score = 100 - (distance * 20)  # Penalize distance
            if is_digit_drop:
                score += 10  # Boost - common STT error

            matches.append(FuzzyMatch(
                known_docket=known,
                distance=distance,
                score=score,
                error_type="digit_drop" if is_digit_drop else
                          "transposition" if is_transposition else "other"
            ))

    return sorted(matches, key=lambda x: x.score, reverse=True)


def is_missing_digit(short: str, long: str) -> bool:
    """Check if short is long with one digit missing."""
    if len(long) - len(short) != 1:
        return False

    # Try removing each digit from long
    for i in range(len(long)):
        if long[:i] + long[i+1:] == short:
            return True
    return False
```

---

## Context Scoring

```python
TRIGGER_PHRASES = {
    # High confidence triggers
    r'docket\s*(?:number|no\.?|#)?\s*': 40,
    r'project\s*(?:number|no\.?|#)?\s*': 40,
    r'case\s*(?:number|no\.?|#)?\s*': 35,
    r'proceeding\s*(?:number|no\.?|#)?\s*': 35,

    # Medium confidence
    r'application\s*': 25,
    r'item\s*(?:number)?\s*\d+[,.]?\s*(?:that\'s|is)?\s*': 20,

    # Low confidence (bare number)
    r'(?:^|\s)': 0,
}

CONTEXT_BOOSTERS = {
    # Utility names nearby
    r'(duke|dominion|firstenergy|aep|ercot|oncor|centerpoint)': 15,

    # Rate case language
    r'(rate\s*case|rate\s*increase|tariff|rate\s*filing)': 10,

    # Regulatory language
    r'(commission|puc|puct|psc|cpuc|hearing|testimony)': 10,
}

def score_context(context_before: str, context_after: str) -> Tuple[int, List[str]]:
    """Score extraction based on surrounding context."""
    score = 0
    clues = []

    full_context = f"{context_before} {context_after}".lower()

    # Check trigger phrases
    for pattern, points in TRIGGER_PHRASES.items():
        if re.search(pattern, context_before, re.I):
            score += points
            clues.append(f"trigger: {pattern}")
            break  # Only count best trigger

    # Check context boosters
    for pattern, points in CONTEXT_BOOSTERS.items():
        if re.search(pattern, full_context, re.I):
            score += points
            clues.append(f"context: {pattern}")

    return min(score, 100), clues
```

---

## Example: Processing "5599"

Input transcript:
> "So let's go then to item number nine. That's project number 5599. Reports of the Electric Reliability Council of Texas."

### Stage 1: Extraction
```
raw_text: "5599"
context_before: "item number nine. That's project number"
context_after: "Reports of the Electric Reliability Council"
trigger_phrase: "project number"
```

### Stage 2: Format Validation
```
TX format: 5-digit number
"5599" = 4 digits
format_valid: FALSE
format_score: 20 (close but wrong length)
```

### Stage 3: Known Docket Matching
```
Exact match: None
Fuzzy search: Found "55999" (distance=1, missing digit)
matched_docket: TX-55999 "ERCOT Reports"
match_type: "fuzzy"
fuzzy_score: 90
```

### Stage 4: Context Analysis
```
trigger "project number": +40
"ercot" in context: +15
"reports" matches known title: +10
context_score: 65
clues: ["trigger: project number", "context: ercot", "title match"]
```

### Stage 5: Confidence Scoring
```
format_score:  20 × 0.25 =  5
match_score:   90 × 0.40 = 36  (fuzzy match to known)
context_score: 65 × 0.25 = 16
fuzzy_bonus:   90 × 0.10 =  9

confidence = 66 → NEEDS_REVIEW
review_reason: "Format invalid (4 digits), fuzzy match to 55999"
```

### Stage 6: Correction Suggestion
```
suggested_correction: "55999"
correction_confidence: 95
evidence: [
    "Missing digit error (5599 → 55999)",
    "Known docket 55999 = 'ERCOT Reports'",
    "Context mentions 'Electric Reliability Council'",
    "Title match: 'Reports' appears in both"
]
```

### Stage 7: Storage
```sql
INSERT INTO extracted_dockets (
    hearing_id, raw_text, normalized_id,
    format_valid, format_score,
    match_type, matched_known_docket_id, fuzzy_score,
    context_score, confidence_score,
    status, review_reason,
    suggested_correction, correction_confidence
) VALUES (
    1697, '5599', 'TX-5599',
    FALSE, 20,
    'fuzzy', 42, 90,  -- 42 = known_dockets.id for 55999
    65, 66,
    'needs_review', 'Format invalid, fuzzy match to 55999',
    '55999', 95
);
```

---

## Review Queue UI

For items with `status = 'needs_review'`:

```
┌─────────────────────────────────────────────────────────────────────┐
│ REVIEW: TX Hearing Dec 18, 2025                                      │
│ Confidence: 66/100                                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│ Extracted: TX-5599                                                   │
│ Context: "...item number nine. That's project number [5599].        │
│           Reports of the Electric Reliability Council of Texas..."   │
│                                                                      │
│ ⚠️ Issues:                                                           │
│   • Format invalid: TX dockets should be 5 digits                   │
│   • No exact match in known dockets                                 │
│                                                                      │
│ 💡 Suggested Correction: TX-55999 (95% confidence)                  │
│   Evidence:                                                          │
│   • Missing digit pattern (5599 → 55999)                            │
│   • Known docket: "Project 55999 - ERCOT Reports"                   │
│   • Context mentions "Electric Reliability Council"                 │
│                                                                      │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ [Accept as 5599]  [Accept as 55999]  [Reject]  [Other...]      │ │
│ └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Migration Path

1. **Add `extracted_dockets` table** - New table for candidates
2. **Keep existing `dockets` table** - For confirmed/accepted dockets only
3. **Update extract stage** - Use new pipeline
4. **Build review queue UI** - For needs_review items
5. **Backfill** - Re-process existing hearings with new pipeline
