# State PSC Docket Format & Metadata Research

## Executive Summary

This document catalogs docket ID formats and metadata availability across all 50 states + DC.

**Key Finding**: There is significant variation in what information can be extracted FROM the docket ID vs what must be scraped FROM the PSC website.

---

## Format Categories

### Category A: Rich Format (Year + Sector/Type encoded in ID)
States where the docket ID contains year, case number, AND utility sector/case type.

### Category B: Year + Sequence Only
States where docket ID has year and sequence but no sector encoding.

### Category C: Simple Sequential
States using just sequential numbers with no embedded metadata.

### Category D: Company-Based
States where docket ID includes company/utility identifier.

---

## Complete State Matrix (All 50 States + DC)

| State | Format | Example | Year | Sector | Type | Category |
|-------|--------|---------|------|--------|------|----------|
| **AL** | NNNNN | 31323 | No | No | No | C |
| **AK** | X-YY-NNN | I-09-007, R-09-002 | Yes | No | Yes (I/R/TL) | B |
| **AZ** | XX-NNNNNN-YY-NNNN | E-00000A-20-0094 | Yes | Yes (E) | No | A |
| **AR** | YY-NNN-X | 24-001-U | Yes | No | No | B |
| **CA** | X.YY-MM-NNN | A.24-07-003 | Yes | **No*** | Yes (A/R/C/I) | B |
| **CO** | YYX-NNNN[XX] | 21A-0625EG | Yes | Yes (E/G) | Yes (A-U) | A |
| **CT** | YY-MM-NN[RE##] | 20-07-01, 95-06-17RE02 | Yes | No | No | B |
| **DE** | YY-NNNN[-X] | 24-0868, 09-277T | Yes | No | Sometimes | B |
| **DC** | FC NNNN / RM-YYYY | FC 1093, RM-2017 | Sometimes | No | Yes (FC/RM/GT) | B |
| **FL** | YYYYNNNN-XX | 20250035-GU | Yes | **Yes** | No | **A** |
| **GA** | NNNNN | 44280 | No | No | No | C |
| **HI** | YYYY-NNNN | 2025-0167 | Yes | No | No | B |
| **ID** | XXX-X-YY-NN | IPC-E-25-15 | Yes | Yes (E) | No | A |
| **IL** | [P]YYYY-NNNN | P2025-0383 | Yes | No | Yes (P) | B |
| **IN** | NNNNN[-sub] | 45159, 38707-FAC | No | No | Subdocket | C |
| **IA** | [prefix]-YY-NNNN | 40+ types | Yes | Varies | Yes | A |
| **KS** | YY-XXXX-NNN-XXX | 08-WHLW-001-COC | Yes | No | **Yes** | A |
| **KY** | YYYY-NNNNN | 2025-00122 | Yes | No | No | B |
| **LA** | X-NNNNN | U-37467, T-37617 | No | **Yes** | Yes (U/T/S/I/R) | A |
| **ME** | YYYY-NNNNN | 2024-00149 | Yes | No | No | B |
| **MD** | NNNN | 9666 | No | No | No | C |
| **MA** | YY-NN or YY-XXX-NN | 24-154, 24-GSEP-04 | Yes | No | Sometimes | B |
| **MI** | U-NNNNN | U-21567 | No | Yes (U) | No | D |
| **MN** | XNNN/XX-YY-NNNN | E002/CN-23-212 | Yes | **Yes** | Yes (CN/M) | **A** |
| **MS** | YYYY-XX-NNN | 2024-UA-135 | Yes | Yes (UA) | No | A |
| **MO** | XX-YYYY-NNNN | WC-2010-0357 | Yes | **Yes** | No | A |
| **MT** | [tracking#] | varies | ? | ? | ? | ? |
| **NE** | XX-NNN | NG-124, MT-0005 | No | **Yes** | No | D |
| **NV** | YY-NNNNN | 15-06042 | Yes | No | No | B |
| **NH** | XX YY-NNN | DE 16-576, DW 20-080 | Yes | **Yes** | No | A |
| **NJ** | XXYYMMNNNNN | ER25040190 | Yes | **Yes** | Yes (R) | **A** |
| **NM** | YY-NNNNN-XX | 23-00255-UT | Yes | **Yes** | No | A |
| **NY** | YY-X-NNNN | 24-E-0314 | Yes | **Yes** | No | A |
| **NC** | X-N,SUB NNN | E-2,SUB 1300 | No | **Yes** | No | D |
| **ND** | XX-YY-NNN | PU-22-001 | Yes | **Yes** | No | A |
| **OH** | YY-NNNN-XX-XXX | 25-0594-EL-AIR | Yes | **Yes** | **Yes** | **A** |
| **OK** | XXX YYYY-NNNNNN | PUD 2022-000093 | Yes | **Yes** | No | A |
| **OR** | XX NNN | UE 439, UM 2225 | No | **Yes** | **Yes** | A |
| **PA** | X-YYYY-NNNNNNN | R-2025-3057164 | Yes | No | Yes (R/M) | B |
| **RI** | YYYY-NNN-TYPE | 2022-001-XXX (new) | Yes | No | Yes | B |
| **SC** | YYYY-NNN-X | 2023-189-E | Yes | **Yes** | No | A |
| **SD** | XX YY-NNN | EL24-011, HP22-001 | Yes | **Yes** | No | **A** |
| **TN** | NNNNNNN | 9900335 | Maybe | No | No | C |
| **TX** | NNNNN | 55599 | No | No | No | C |
| **UT** | YY-XXX-NN | 09-049-86 | Yes | No | No | D |
| **VT** | YY-NNNN-XXX | 25-2441-PET | Yes | No | **Yes** | B |
| **VA** | XXX-YYYY-NNNNN | PUR-2024-00144 | Yes | No | Yes (PUR) | B |
| **WA** | XX-YYNNNN | UE-210223 | Yes | **Yes** | No | A |
| **WV** | YY-NNNN-X-X | 08-1500-E-C | Yes | **Yes** | Yes (C) | **A** |
| **WI** | NNNN-XX-NNN | 2669-TI-100 | No | **Yes** | No | D |
| **WY** | NNNNN-NNN-XX-YY | 20000-676-EA-24 | Yes | No | **Yes** | D |

*CA's prefix (A/R/C/I) indicates proceeding TYPE (Application, Rulemaking, Complaint, Investigation), NOT utility sector

---

## States with Utility Sector Encoded in Docket ID

**22 states** encode utility sector in the docket ID:

| State | Electric | Gas | Water | Telecom | Other |
|-------|----------|-----|-------|---------|-------|
| **AZ** | E | - | - | - | - |
| **CO** | E suffix | G suffix | - | - | - |
| **FL** | EU, EI, EP | GU, GP | WU, WP, WS | TU, TL | OT, SU |
| **ID** | E | - | - | - | - |
| **LA** | U | - | - | T | S, I, R, X |
| **MN** | E prefix | G prefix | W prefix | - | - |
| **MO** | E prefix | G prefix | W prefix | - | - |
| **NE** | (implied) | NG | - | - | MT |
| **NH** | DE | DG | DW | - | DRM |
| **NJ** | ER, EO | GR, GO | WR, WO | - | AO, AX |
| **NM** | UT | UT | UT | - | - |
| **NY** | E | G | W | C | M |
| **NC** | E | G | W | - | - |
| **ND** | PU | PU | - | - | RC, AM |
| **OH** | EL | GA | WW, WS | TL | TR, RR |
| **OK** | PUD | PUD | PUD | - | - |
| **OR** | UE | UG | UW | - | UM |
| **SC** | E | - | - | C | T, A |
| **SD** | EL | - | - | TC | HP |
| **WA** | UE | UG | - | UT | TG, TR |
| **WV** | E | G | W | - | - |
| **WI** | ER | GR | - | TI | - |

---

## States with Case Type Encoded in Docket ID

**15 states** encode case/proceeding type:

| State | Rate Case | Application | Complaint | Investigation | Rulemaking | Other |
|-------|-----------|-------------|-----------|---------------|------------|-------|
| **AK** | - | - | - | I | R | TL |
| **CA** | - | A | C | I | R | - |
| **CO** | - | A | F | I | R | B, D, Q, L, M, etc. |
| **KS** | COC | - | - | - | - | TRA, CEXC |
| **LA** | - | - | - | I | R | U, T, S, X |
| **NJ** | R suffix | - | - | - | - | O suffix |
| **OH** | AIR | - | - | - | - | SSO, ATA, RDR, UNC |
| **OR** | - | - | - | - | - | E, M |
| **PA** | R | - | - | - | M | - |
| **RI** | - | - | - | - | - | TYPE suffix |
| **VA** | - | - | - | - | - | PUR, CLK |
| **VT** | - | PET | - | INV | - | TF, NM |
| **WV** | - | - | C | - | - | - |
| **WY** | - | - | - | - | - | EA, ER, CT, GM, etc. |

---

## Summary Statistics

| Metric | Count | Percentage |
|--------|-------|------------|
| **Total jurisdictions** | 51 (50 states + DC) | 100% |
| **Year in ID** | 40 | 78% |
| **Sector in ID** | 22 | 43% |
| **Case Type in ID** | 15 | 29% |
| **Both Sector + Type** | 8 | 16% |
| **Simple sequential only** | 7 | 14% |
| **Company-based** | 6 | 12% |

### Highest Value Formats (Sector + Type encoded)
1. **OH** - `YY-NNNN-XX-XXX` (year, sector, case type)
2. **CO** - `YYX-NNNN[XX]` (year, case type, optional sector)
3. **WV** - `YY-NNNN-X-X` (year, sector, case type)
4. **NJ** - `XXYYMMNNNNN` (sector, year, month, rate indicator)
5. **MN** - `XNNN/XX-YY-NNNN` (company, type, year)
6. **FL** - `YYYYNNNN-XX` (year, sector) - no type but very structured
7. **OR** - `XX NNN` (sector + case type combined)
8. **LA** - `X-NNNNN` (sector/type prefix)

### Lowest Information Formats
1. **AL** - `NNNNN` (sequential only)
2. **GA** - `NNNNN` (sequential only)
3. **TX** - `NNNNN` (sequential only)
4. **MD** - `NNNN` (sequential only)
5. **TN** - `NNNNNNN` (sequential, maybe year prefix)
6. **IN** - `NNNNN` (sequential with subdockets)

---

## Recommendations for Schema Design

### 1. Fields FROM Docket ID (Parser)
```
year           INTEGER      -- Available in ~78% of states
case_number    INTEGER      -- Universal (sequence number)
raw_prefix     VARCHAR(10)  -- Store raw, interpret per-state
raw_suffix     VARCHAR(10)  -- Store raw, interpret per-state
```

### 2. Fields DERIVED from ID (State-specific mapping)
```
utility_sector VARCHAR(20)  -- electric/gas/water/telecom (~43% of states)
docket_type    VARCHAR(50)  -- rate_case/application/complaint (~29% of states)
company_code   VARCHAR(20)  -- For company-based systems (~12% of states)
```

### 3. Fields FROM Website (Scraper - always authoritative)
```
title              TEXT         -- Case/proceeding title
utility_name       VARCHAR(200) -- Company name
filing_date        DATE         -- When filed
status             VARCHAR(20)  -- Open/closed/pending
assigned_judge     VARCHAR(100) -- ALJ assignment
assigned_commissioner VARCHAR(100) -- Commissioner
parties            JSONB        -- List of parties
documents_count    INTEGER      -- Number of documents
```

### 4. Reconciliation Rules

**Priority Order for `utility_sector`:**
1. Website scraper (most authoritative)
2. Docket ID parser (if state encodes it)
3. Text inference from title/description

**Keep Separate:**
- `docket_type` (proceeding type: rate case, application, complaint)
- `utility_sector` (industry: electric, gas, water, telecom)

These are **different concepts** - don't conflate them.

---

## Implementation Priority

### Tier 1: High-value markets with rich ID format
1. **OH** - Complex but highly informative format
2. **FL** - Large market, sector encoded
3. **NY** - Large market, sector encoded
4. **CA** - Large market, type encoded (not sector!)
5. **TX** - Large market but simple ID (need scraper)

### Tier 2: Medium markets with useful ID format
6. **CO** - Rich format with type codes
7. **NJ** - Dense format with sector+type
8. **PA** - Large market, type prefix
9. **WA** - Sector encoded
10. **MN** - Complex but informative

### Tier 3: Other states
- Implement generic parser + rely on scraping
