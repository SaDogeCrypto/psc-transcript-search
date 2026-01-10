# Florida PSC Data Pipeline Audit

## Executive Summary

**CRITICAL FINDING**: The data pipeline has fundamental architectural issues that cause cascading data quality problems. The root cause is that **docket_number linkage is optional and inconsistently formatted across all pipelines**.

### Key Statistics
- **fl_dockets**: 565 valid records (after cleanup of ~2,126 junk records)
- **fl_documents**: 8,620 total, **5,621 (65%) have NULL docket_number**
- **fl_hearings**: 77 total, **42 have NULL docket_number**
- **fl_hearing_dockets (junction)**: Empty - not being populated by any pipeline

---

## 1. DATA INGESTION SOURCES

### 1a. Florida Channel RSS Scraper

**Location**: `src/florida/scraper.py`

| Aspect | Detail |
|--------|--------|
| **Trigger** | Manual via API or CLI |
| **Tables Written** | `fl_hearings` |
| **Docket Extraction** | **NONE** - does not extract docket_number |
| **Link Creation** | Does not link to dockets |

**How it works**:
```python
hearing = FLHearing(
    title=item.title,
    hearing_date=item.pub_date,
    hearing_type=_infer_hearing_type(item.title),
    source_type="video",
    source_url=item.link,
    external_id=item.guid,
    transcript_status=None,
)
```

**PROBLEM**: Creates hearings with `docket_number=NULL`. The RSS feed doesn't include docket numbers, and there's no post-processing to extract them from titles like "10/15/24 - FPL Rate Case (Docket No. 20250011-EI)".

---

### 1b. Thunderstone Scraper

**Location**: `src/florida/scrapers/thunderstone.py`

| Aspect | Detail |
|--------|--------|
| **Trigger** | Called by ThunderstoneImporter service |
| **Tables Written** | None (data class only) |
| **Docket Extraction** | Regex: `\b(\d{4}\d{4})-?([A-Z]{2})\b` (allows optional hyphen) |

**How it extracts docket_number**:
```python
DOCKET_PATTERN = re.compile(r'\b(\d{4}\d{4})-?([A-Z]{2})\b')

def _extract_docket_number(self, text: str) -> Optional[str]:
    match = self.DOCKET_PATTERN.search(text)
    if match:
        return f"{match.group(1)}-{match.group(2)}"  # Always adds hyphen
```

**PROBLEM**: The pattern `(\d{4}\d{4})-?([A-Z]{2})` allows both `20250011-EI` and `20250011EI` (no hyphen), but always outputs with hyphen. However, this only works if the docket number appears in title/content/URL.

---

### 1c. Thunderstone Importer (THE MAIN INGESTION PIPELINE)

**Location**: `src/florida/services/thunderstone_import.py`

| Aspect | Detail |
|--------|--------|
| **Trigger** | Manual via script or CLI |
| **Tables Written** | `fl_documents`, `fl_dockets` |
| **Docket Extraction** | Regex: `\b((?:19\|20)\d{2})(\d{4})-([A-Z]{2})\b` (REQUIRES hyphen) |

**How it determines docket_number**:
```python
DOCKET_PATTERN = re.compile(r'\b((?:19|20)\d{2})(\d{4})-([A-Z]{2})\b')

def _import_document(self, session, doc):
    docket_info = (
        self._extract_docket_info(doc.title or '') or
        self._extract_docket_info(doc.content_excerpt or '') or
        self._extract_docket_info(doc.file_url or '')
    )
    if docket_info:
        docket_number = ...  # Use extracted
        self._get_or_create_docket(...)  # Creates docket if missing
    # Creates document with docket_number (may be None)
```

**How it links tables**:
- Creates `FLDocket` if docket number found and doesn't exist
- Sets `FLDocument.docket_number` (FK to dockets)
- Does NOT create `FLHearingDocket` links

**PROBLEMS**:
1. **65% of documents** have NULL docket_number because the search was done with generic terms like "Florida" rather than specific docket numbers
2. Many older documents don't have docket numbers in title/content/URL
3. The scraper's docket pattern allows optional hyphen, but the importer REQUIRES hyphen - format mismatch

---

### 1d. ClerkOffice Scraper

**Location**: `src/florida/scrapers/clerkoffice.py`

| Aspect | Detail |
|--------|--------|
| **Trigger** | Called by DocketSyncStage |
| **Tables Written** | `fl_dockets` (via DocketSyncStage) |
| **Docket Format** | From API: `YYYYNNNN-XX` (proper format) |

**How it determines docket_number**:
```python
DOCKET_PATTERN = re.compile(r'^(\d{4})(\d{4})-([A-Z]{2})$')

def _parse_api_result(self, item):
    docket_number = item.get('docketnum') or str(item.get('docketId', ''))
    # Parse components from proper format
    components = self.parse_docket_number(docket_number)
```

**This is the CORRECT source for dockets**. The API returns properly formatted docket numbers with official metadata.

---

### 1e. DocketSyncStage

**Location**: `src/florida/pipeline/docket_sync.py`

| Aspect | Detail |
|--------|--------|
| **Trigger** | Scheduled or manual |
| **Tables Written** | `fl_dockets` |
| **Link Creation** | None - only creates dockets |

**GOOD**: This is the proper way to populate `fl_dockets`. It uses the official ClerkOffice API.

**PROBLEM**: Not being run regularly. Many dockets were created by ThunderstoneImporter with bad/incomplete data instead of from official source.

---

### 1f. DocumentSyncStage

**Location**: `src/florida/pipeline/document_sync.py`

| Aspect | Detail |
|--------|--------|
| **Trigger** | Manual or by docket |
| **Tables Written** | `fl_documents` |
| **Link Validation** | Validates docket exists before setting FK |

```python
def _upsert_document(self, doc):
    validated_docket_number = None
    if doc.docket_number:
        docket_exists = self.db.query(FLDocket).filter(
            FLDocket.docket_number == doc.docket_number
        ).first()
        if docket_exists:
            validated_docket_number = doc.docket_number
```

**GOOD**: Validates docket exists before setting FK.
**PROBLEM**: If docket doesn't exist, document gets NULL docket_number rather than creating the docket.

---

### 1g. Transcript Parser / load_transcripts.py

**Location**: `src/florida/services/transcript_parser.py`, `scripts/load_transcripts.py`

| Aspect | Detail |
|--------|--------|
| **Trigger** | Manual script |
| **Tables Written** | `fl_hearings`, `fl_transcript_volumes`, `fl_speaker_turns`, `fl_transcript_witnesses`, etc. |
| **Docket Extraction** | Parses from PDF header: `DOCKET NO.: 20250011-EI` |

**How it determines docket_number**:
```python
# In transcript_parser.py
def _parse_metadata(self, pages, filename):
    match = re.search(r'DOCKET\s+NO\.?:?\s*([\d\-]+\-[A-Z]+)', text, re.IGNORECASE)
    if match:
        metadata.docket_number = match.group(1).strip()
```

**How it links**:
```python
# In load_transcripts.py
def get_or_create_docket(session, docket_number):
    # Creates docket if doesn't exist (GOOD)

def get_or_create_hearing(session, parsed):
    # Creates hearing if doesn't exist
    # Sets hearing.docket_number (GOOD)
```

**GOOD**: This pipeline properly extracts docket numbers and creates missing dockets.
**STILL MISSING**: Does not populate `FLHearingDocket` junction table.

---

## 2. DOCKET NUMBER HANDLING COMPARISON

| Pipeline | Source of docket_number | Format Required | Creates Docket? | Sets FK? |
|----------|------------------------|-----------------|-----------------|----------|
| RSS Scraper | **NONE** | N/A | No | No |
| Thunderstone Scraper | Title/Content/URL | `YYYYNNNN-?XX` (optional hyphen) | N/A | N/A |
| Thunderstone Importer | Title/Content/URL | `YYYYNNNN-XX` (required hyphen) | Yes | Yes |
| ClerkOffice Scraper | API field | `YYYYNNNN-XX` | Yes | N/A |
| DocketSyncStage | API field | `YYYYNNNN-XX` | Yes | N/A |
| DocumentSyncStage | Scraper output | Any | No | Yes (if docket exists) |
| Transcript Parser | PDF text | `YYYYNNNN-XX` | Yes | Yes |
| load_transcripts.py | Parser output | `YYYYNNNN-XX` | Yes | Yes |

### Format Inconsistencies

The codebase has THREE different docket patterns:

1. **Scraper pattern** (allows optional hyphen):
   ```python
   r'\b(\d{4}\d{4})-?([A-Z]{2})\b'
   ```

2. **Importer pattern** (requires hyphen):
   ```python
   r'\b((?:19|20)\d{2})(\d{4})-([A-Z]{2})\b'
   ```

3. **Validation pattern** (strict):
   ```python
   r'^(\d{4})(\d{4})-([A-Z]{2})$'
   ```

This causes **2,281 documents** to have old format without sector suffix.

---

## 3. RELATIONSHIP INTEGRITY

### fl_documents.docket_number → fl_dockets.docket_number

| Metric | Count | Percentage |
|--------|-------|------------|
| Documents with valid docket FK | ~3,000 | ~35% |
| Documents with NULL docket_number | 5,621 | 65% |
| Documents with wrong format (no suffix) | 2,281 | ~26% |

**ROOT CAUSES**:
1. ThunderstoneImporter searched with generic terms, not docket-specific
2. Many older documents don't have docket numbers in metadata
3. Format mismatch between scraper and importer patterns

---

### fl_hearings.docket_number → fl_dockets.docket_number

| Metric | Count |
|--------|-------|
| Hearings with docket_number | 35 |
| Hearings with NULL docket_number | 42 |
| Hearings with invalid format | 24 (have "20260000" invalid) |

**ROOT CAUSE**: RSS scraper doesn't extract docket numbers from titles.

---

### fl_hearing_dockets (junction table) - COMPLETELY EMPTY

| Metric | Count |
|--------|-------|
| Records | 0 |

**ROOT CAUSE**: **No pipeline populates this table**. The entity linking stage was designed but never completed.

This means:
- API queries using this junction return 0 hearings
- The many-to-many relationship design was never implemented

---

### fl_transcript_volumes.hearing_id → fl_hearings.id

| Status | Notes |
|--------|-------|
| **Working** | load_transcripts.py properly creates this link |

**But**: The hearing might not link to a docket if it was created without one.

---

### fl_case_events.source_id → source tables

| Status | Notes |
|--------|-------|
| Partially working | Depends on source data having proper docket_number |

**Problem**: If the source document/hearing has NULL docket_number, the event can't be properly linked.

---

## 4. THE IDEAL STATE

### 4a. Docket as the Anchor

**Rule**: Every piece of data MUST link to a docket. No orphans.

```
fl_dockets (source of truth)
    ↑
    ├── fl_documents.docket_number (FK)
    ├── fl_hearings.docket_number (FK)
    ├── fl_case_events.docket_number (FK)
    └── fl_hearing_dockets (many-to-many junction)
            ↓
        fl_hearings
            ↓
        fl_transcript_volumes
            ↓
        fl_speaker_turns
```

### 4b. Document Ingestion (Ideal)

```python
def ingest_document(doc):
    # Step 1: Extract docket number (required)
    docket_number = extract_docket_number(doc)
    if not docket_number:
        # Try harder: parse PDF, check URL patterns, etc.
        docket_number = deep_extract_docket(doc)

    if not docket_number:
        raise ValueError("Cannot determine docket - marking for review")

    # Step 2: Normalize format
    docket_number = normalize_docket_format(docket_number)  # Always YYYYNNNN-XX

    # Step 3: Ensure docket exists (create from ClerkOffice API if needed)
    docket = get_or_fetch_docket(docket_number)

    # Step 4: Create document with FK
    document = FLDocument(docket_number=docket_number, ...)
```

### 4c. Hearing Ingestion (Ideal)

```python
def ingest_hearing(hearing_data):
    # Step 1: Extract docket from title/description
    docket_numbers = extract_dockets_from_title(hearing_data.title)

    if not docket_numbers:
        # Mark for manual review, but still create hearing
        hearing.needs_docket_review = True

    # Step 2: Create hearing
    hearing = FLHearing(...)

    # Step 3: Create junction table entries (many-to-many)
    for docket_number in docket_numbers:
        link = FLHearingDocket(
            hearing_id=hearing.id,
            docket_id=get_docket_id(docket_number),
            is_primary=(docket_number == docket_numbers[0])
        )
```

### 4d. Transcript Ingestion (Ideal)

```python
def ingest_transcript(pdf_path):
    # Step 1: Parse metadata
    parsed = parser.parse_file(pdf_path)

    # Step 2: Ensure docket exists
    docket = get_or_fetch_docket(parsed.metadata.docket_number)

    # Step 3: Find or create hearing
    hearing = get_or_create_hearing(
        docket_number=docket.docket_number,
        hearing_date=parsed.metadata.hearing_date
    )

    # Step 4: Create junction if not exists
    ensure_hearing_docket_link(hearing.id, docket.id)

    # Step 5: Create transcript volume
    volume = FLTranscriptVolume(hearing_id=hearing.id, ...)
```

---

## 5. WHAT'S BROKEN (GAP ANALYSIS)

### Pipeline 1: RSS Scraper → fl_hearings

| Issue | Cause | Fix Type |
|-------|-------|----------|
| No docket extraction | RSS feed doesn't include docket | Code change (ongoing) |
| No junction table links | Feature not implemented | Code change (ongoing) |

**Required Fix**:
```python
# In scraper.py, after creating hearing:
def _extract_docket_from_title(title: str) -> Optional[str]:
    """Extract docket number from hearing title."""
    match = re.search(r'\b(\d{8})-([A-Z]{2})\b', title)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    # Also try: "Docket No. 20250011-EI" format
    match = re.search(r'Docket\s+(?:No\.?\s*)?(\d+)-([A-Z]{2})', title, re.IGNORECASE)
    ...
```

---

### Pipeline 2: Thunderstone Importer → fl_documents, fl_dockets

| Issue | Cause | Fix Type |
|-------|-------|----------|
| 65% NULL docket_number | Generic search terms | Re-run with specific searches (one-time) |
| Pattern mismatch | Scraper allows optional hyphen | Code change (ongoing) |
| No docket enrichment from API | Only uses doc metadata | Code change (ongoing) |

**Required Fixes**:
1. **Re-index documents by docket** (one-time):
   ```bash
   for each docket in fl_dockets:
       search_and_index_documents(docket.docket_number)
   ```

2. **Fix pattern consistency** (ongoing):
   ```python
   # Standardize on: YYYYNNNN-XX (required hyphen)
   DOCKET_PATTERN = re.compile(r'\b((?:19|20)\d{2})(\d{4})-([A-Z]{2})\b')
   ```

3. **Enrich from ClerkOffice API** (ongoing):
   ```python
   def _get_or_create_docket(self, docket_number, doc):
       if docket_number not in self._existing_dockets:
           # Fetch from official API first
           official_data = clerkoffice_client.get_docket_details(docket_number)
           if official_data:
               return create_docket_from_api(official_data)
           # Fall back to doc metadata
           return create_docket_from_doc(doc)
   ```

---

### Pipeline 3: DocketSyncStage → fl_dockets

| Issue | Cause | Fix Type |
|-------|-------|----------|
| Not run regularly | No scheduler | Infra change |
| Doesn't update documents | Not its responsibility | N/A |

**Required Fix**: Run DocketSyncStage before any document ingestion to ensure dockets exist.

---

### Pipeline 4: Junction Table (fl_hearing_dockets) - NOT POPULATED

| Issue | Cause | Fix Type |
|-------|-------|----------|
| Table is empty | No pipeline writes to it | Code change (ongoing) |

**Required Fix**: Add junction table population to all hearing-related pipelines:

```python
# After creating/finding hearing with docket_number:
if hearing.docket_number:
    docket = session.query(FLDocket).filter(
        FLDocket.docket_number == hearing.docket_number
    ).first()
    if docket:
        existing_link = session.query(FLHearingDocket).filter(
            FLHearingDocket.hearing_id == hearing.id,
            FLHearingDocket.docket_id == docket.id
        ).first()
        if not existing_link:
            session.add(FLHearingDocket(
                hearing_id=hearing.id,
                docket_id=docket.id,
                is_primary=True
            ))
```

---

## 6. MIGRATION PLAN

### Phase 1: Fix the Pipelines (Prevents Future Bad Data)

**Priority 1 - Critical**:
1. **Add docket extraction to RSS scraper** (`src/florida/scraper.py`)
2. **Populate FLHearingDocket junction table** in all hearing pipelines
3. **Standardize docket pattern** across all files

**Priority 2 - Important**:
4. **Add validation layer** to reject documents without docket_number
5. **Enrich dockets from ClerkOffice API** before using doc metadata

### Phase 2: Clean Up Existing Data (One-Time)

**Script 1: Backfill document docket_numbers**
```sql
-- Documents with docket_number in URL pattern
UPDATE fl_documents
SET docket_number = regexp_extract(file_url, '(\d{8})-([A-Z]{2})')
WHERE docket_number IS NULL
AND file_url ~ '\d{8}-[A-Z]{2}';
```

**Script 2: Link hearings to dockets**
```python
for hearing in session.query(FLHearing).filter(FLHearing.docket_number.isnot(None)):
    docket = session.query(FLDocket).filter(
        FLDocket.docket_number == hearing.docket_number
    ).first()
    if docket and not existing_link:
        session.add(FLHearingDocket(hearing_id=hearing.id, docket_id=docket.id))
```

**Script 3: Re-sync dockets from official API**
```bash
python -c "
from florida.pipeline.docket_sync import DocketSyncStage
from florida.models import SessionLocal
stage = DocketSyncStage(SessionLocal())
stage.sync_all(limit=10000)
"
```

**Script 4: Re-index documents by docket**
```python
for docket in session.query(FLDocket).filter(FLDocket.status == 'open'):
    document_sync.index_docket_documents(docket.docket_number)
```

### Phase 3: Validation Rules (Ongoing)

Add database constraints and application validation:

```python
# In document creation
if not docket_number:
    raise ValidationError("Document must have docket_number")

# In hearing creation
if not docket_number and not title_contains_docket_pattern(title):
    hearing.needs_review = True
    logger.warning(f"Hearing {hearing.id} has no docket - marked for review")
```

---

## 7. RECOMMENDED EXECUTION ORDER

1. **Immediate** (today):
   - Run `DocketSyncStage.sync_all()` to get official dockets
   - Run backfill script to populate `FLHearingDocket` from existing `FLHearing.docket_number`

2. **This week**:
   - Fix RSS scraper to extract docket from title
   - Add junction table population to load_transcripts.py
   - Standardize docket pattern in thunderstone_import.py

3. **Next sprint**:
   - Re-index documents by docket number
   - Add validation layer to reject orphan documents
   - Set up scheduled DocketSyncStage runs

4. **Future**:
   - Add ML-based docket extraction for edge cases
   - Build review queue for unlinked hearings/documents

---

## Appendix: File Locations

| Component | File |
|-----------|------|
| RSS Scraper | `src/florida/scraper.py` |
| Thunderstone Scraper | `src/florida/scrapers/thunderstone.py` |
| Thunderstone Importer | `src/florida/services/thunderstone_import.py` |
| ClerkOffice Scraper | `src/florida/scrapers/clerkoffice.py` |
| DocketSyncStage | `src/florida/pipeline/docket_sync.py` |
| DocumentSyncStage | `src/florida/pipeline/document_sync.py` |
| Transcript Parser | `src/florida/services/transcript_parser.py` |
| Transcript Loader | `scripts/load_transcripts.py` |
| Backfill Script | `scripts/backfill_dockets_from_documents.py` |

| Model | File |
|-------|------|
| FLDocket | `src/florida/models/docket.py` |
| FLDocument | `src/florida/models/document.py` |
| FLHearing | `src/florida/models/hearing.py` |
| FLHearingDocket | `src/florida/models/linking.py` |
| FLTranscriptVolume | `src/florida/models/transcript.py` |
| FLCaseEvent | `src/florida/models/sales.py` |
