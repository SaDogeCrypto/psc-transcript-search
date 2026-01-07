"""
Parse docket numbers into structured components.
Each state has different formats.

Key distinction:
- utility_sector: Industry type (electric, gas, water, telecom)
- docket_type: Proceeding type (rate_case, application, complaint, investigation, rulemaking)

These are DIFFERENT concepts - some states encode one, some encode the other, some encode both.
"""

import re
from dataclasses import dataclass
from typing import Optional, Dict, Callable


@dataclass
class ParsedDocket:
    """Parsed docket number with structured components."""
    raw: str
    state_code: str
    normalized_id: str

    # Structural components from ID
    year: Optional[int] = None
    case_number: Optional[int] = None
    prefix: Optional[str] = None  # Raw prefix from ID
    suffix: Optional[str] = None  # Raw suffix from ID

    # Derived/interpreted fields
    utility_sector: Optional[str] = None  # electric, gas, water, telecom
    docket_type: Optional[str] = None     # rate_case, application, complaint, investigation, rulemaking
    company_code: Optional[str] = None    # For company-based systems (UT, WI, MN, NC)


# =============================================================================
# UTILITY SECTOR MAPPINGS (Industry: electric, gas, water, telecom)
# =============================================================================
SECTOR_MAPPINGS: Dict[str, Dict[str, str]] = {
    'FL': {
        'EU': 'electric', 'EI': 'electric', 'EP': 'electric',
        'GU': 'gas', 'GP': 'gas',
        'WU': 'water', 'WP': 'water', 'WS': 'water',
        'TU': 'telecom', 'TL': 'telecom', 'TP': 'telecom',
        'SU': 'water',  # Sewer
        'OT': 'other',
    },
    'OH': {
        'EL': 'electric',
        'GA': 'gas',
        'WW': 'water', 'WS': 'water',
        'TL': 'telecom',
        'TR': 'transportation', 'RR': 'transportation',
    },
    'NY': {
        'E': 'electric',
        'G': 'gas',
        'W': 'water',
        'C': 'telecom',  # Communications
        'M': 'other',    # Miscellaneous
    },
    'NC': {
        'E': 'electric',
        'G': 'gas',
        'W': 'water',
        'T': 'telecom',
    },
    'WA': {
        'UE': 'electric',
        'UG': 'gas',
        'UW': 'water',
        'UT': 'telecom',
        'TG': 'other',  # Solid waste
        'TR': 'transportation',
    },
    'OR': {
        'UE': 'electric',
        'UG': 'gas',
        'UW': 'water',
        'UM': 'other',  # Miscellaneous
    },
    'NJ': {
        'E': 'electric',
        'G': 'gas',
        'W': 'water',
        'A': 'other',  # Administrative
    },
    'SC': {
        'E': 'electric',
        'G': 'gas',
        'W': 'water',
        'C': 'telecom',
        'T': 'transportation',
    },
    'SD': {
        'EL': 'electric',
        'NG': 'gas',
        'TC': 'telecom',
        'HP': 'other',  # Hydrocarbon pipeline
    },
    'NH': {
        'DE': 'electric',
        'DG': 'gas',
        'DW': 'water',
        'DT': 'telecom',
    },
    'WV': {
        'E': 'electric',
        'G': 'gas',
        'W': 'water',
    },
    'MO': {
        'E': 'electric',
        'G': 'gas',
        'W': 'water',
        'S': 'water',  # Sewer
        'T': 'telecom',
    },
    'WI': {
        'ER': 'electric',
        'GR': 'gas',
        'WR': 'water',
        'TI': 'telecom',
    },
    'ND': {
        'PU': 'electric',  # Public Utility (usually electric/gas)
    },
    'NE': {
        'NG': 'gas',
        'EL': 'electric',
    },
    'LA': {
        'U': 'electric',  # Utility (usually electric)
        'T': 'transportation',
    },
    'ID': {
        'E': 'electric',
        'G': 'gas',
        'W': 'water',
    },
    'AZ': {
        'E': 'electric',
        'G': 'gas',
        'W': 'water',
        'S': 'water',  # Sewer
    },
    'CO': {
        'E': 'electric',
        'G': 'gas',
        'EG': 'electric',  # Combined
    },
    'MS': {
        'UA': 'electric',  # Utility Application
    },
    'NM': {
        'UT': 'electric',  # Utility (context determines actual sector)
    },
    'OK': {
        'PUD': 'electric',  # Public Utility Division
    },
}


# =============================================================================
# DOCKET TYPE MAPPINGS (Proceeding: rate_case, application, complaint, etc.)
# =============================================================================
DOCKET_TYPE_MAPPINGS: Dict[str, Dict[str, str]] = {
    'CA': {
        'A': 'application',
        'C': 'complaint',
        'I': 'investigation',
        'R': 'rulemaking',
        'P': 'petition',
    },
    'OH': {
        'AIR': 'rate_case',      # Application to Increase Rates
        'SSO': 'rate_case',      # Standard Service Offer
        'ATA': 'tariff',         # Amended Tariff Application
        'UNC': 'other',          # Miscellaneous
        'RDR': 'rate_case',      # Rider
        'BGN': 'certificate',    # Certificate (Board of Geographic Names)
        'COI': 'complaint',
    },
    'CO': {
        'A': 'application',
        'AL': 'tariff',         # Advice Letter
        'C': 'complaint',       # Commission Complaint
        'F': 'complaint',       # Formal Complaint
        'I': 'investigation',
        'R': 'rulemaking',
        'Q': 'inquiry',
        'M': 'other',           # Miscellaneous
    },
    'KS': {
        'COC': 'certificate',   # Certificate of Convenience
        'TRA': 'transportation',
        'RTS': 'rate_case',
    },
    'PA': {
        'R': 'rate_case',
        'C': 'complaint',
        'M': 'other',           # Miscellaneous
        'A': 'application',
    },
    'NJ': {
        'R': 'rate_case',       # Rate (ER = Electric Rate)
        'O': 'other',           # Order/Other (EO = Electric Order)
    },
    'VT': {
        'PET': 'petition',
        'TF': 'tariff',
        'NM': 'other',          # Net Metering
        'INV': 'investigation',
    },
    'AK': {
        'I': 'investigation',
        'R': 'rulemaking',
        'TL': 'tariff',
    },
    'LA': {
        'U': 'application',     # Utility application
        'I': 'investigation',
        'R': 'rulemaking',
        'S': 'other',           # Securities
        'T': 'transportation',
        'X': 'other',           # Repository
    },
    'WV': {
        'C': 'complaint',
        'R': 'rate_case',
        'G': 'general',
    },
    'WY': {
        'EA': 'application',
        'ER': 'rate_case',
        'CT': 'certificate',
        'GM': 'general',
    },
    'NH': {
        'DRM': 'rulemaking',
    },
}


def parse_docket(raw: str, state_code: str) -> ParsedDocket:
    """
    Parse a docket number based on state format.

    Args:
        raw: Raw docket number string
        state_code: Two-letter state code

    Returns:
        ParsedDocket with structured components
    """
    raw = raw.strip().upper()
    state_code = state_code.upper()

    # Remove state prefix if present
    cleaned = re.sub(rf'^{state_code}[-\s]*', '', raw)

    # Try state-specific parsing
    parser = STATE_PARSERS.get(state_code, parse_generic)
    return parser(raw, cleaned, state_code)


# =============================================================================
# STATE-SPECIFIC PARSERS
# =============================================================================

def parse_florida(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    Florida format: YYYYNNNN-XX
    Example: 20250035-GU (Year 2025, Case 35, Gas Utility)
    Sector: YES (from suffix)
    Type: NO
    """
    match = re.match(r'(\d{4})(\d{4})-?([A-Z]{2})?', cleaned)

    if match:
        year = int(match.group(1))
        case_num = int(match.group(2))
        suffix = match.group(3)
        sector = SECTOR_MAPPINGS.get('FL', {}).get(suffix) if suffix else None

        normalized = f"FL-{year}{case_num:04d}"
        if suffix:
            normalized += f"-{suffix}"

        return ParsedDocket(
            raw=raw, state_code='FL', normalized_id=normalized,
            year=year, case_number=case_num, suffix=suffix,
            utility_sector=sector
        )

    # Try just numeric (8 digits)
    num_match = re.match(r'(\d{8})', cleaned)
    if num_match:
        num = num_match.group(1)
        year = int(num[:4])
        case_num = int(num[4:])
        return ParsedDocket(
            raw=raw, state_code='FL', normalized_id=f"FL-{year}{case_num:04d}",
            year=year, case_number=case_num
        )

    return ParsedDocket(raw=raw, state_code='FL', normalized_id=f"FL-{cleaned}")


def parse_ohio(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    Ohio format: YY-NNNN-XX-XXX
    Example: 25-0594-EL-AIR (Year 2025, Case 594, Electric, Rate Case)
    Sector: YES (EL, GA, WW, TL)
    Type: YES (AIR, SSO, ATA, RDR, UNC)
    """
    # Full format: YY-NNNN-XX-XXX
    match = re.match(r'(\d{2})-?(\d{4})-?([A-Z]{2})-?([A-Z]{2,3})', cleaned)

    if match:
        year_2d = int(match.group(1))
        case_num = int(match.group(2))
        sector_code = match.group(3)
        type_code = match.group(4)

        full_year = 2000 + year_2d if year_2d < 50 else 1900 + year_2d
        sector = SECTOR_MAPPINGS.get('OH', {}).get(sector_code)
        docket_type = DOCKET_TYPE_MAPPINGS.get('OH', {}).get(type_code)

        normalized = f"OH-{year_2d:02d}-{case_num:04d}-{sector_code}-{type_code}"

        return ParsedDocket(
            raw=raw, state_code='OH', normalized_id=normalized,
            year=full_year, case_number=case_num,
            prefix=sector_code, suffix=type_code,
            utility_sector=sector, docket_type=docket_type
        )

    # Partial format: YY-NNNN-XX (no type)
    match2 = re.match(r'(\d{2})-?(\d{4})-?([A-Z]{2})', cleaned)
    if match2:
        year_2d = int(match2.group(1))
        case_num = int(match2.group(2))
        sector_code = match2.group(3)

        full_year = 2000 + year_2d if year_2d < 50 else 1900 + year_2d
        sector = SECTOR_MAPPINGS.get('OH', {}).get(sector_code)

        return ParsedDocket(
            raw=raw, state_code='OH', normalized_id=f"OH-{year_2d:02d}-{case_num:04d}-{sector_code}",
            year=full_year, case_number=case_num, prefix=sector_code,
            utility_sector=sector
        )

    return ParsedDocket(raw=raw, state_code='OH', normalized_id=f"OH-{cleaned}")


def parse_california(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    California format: X.YY-MM-NNN
    Example: A.24-07-003 (Application, 2024, July, Case 3)
    Sector: NO - prefix is case TYPE not sector!
    Type: YES (A=Application, R=Rulemaking, C=Complaint, I=Investigation)
    """
    # Standard format: A.24-07-003
    match = re.match(r'([A-Z])\.?(\d{2})-?(\d{2})-?(\d{3})', cleaned)

    if match:
        prefix = match.group(1)
        year = int(match.group(2))
        month = int(match.group(3))
        case_num = int(match.group(4))

        full_year = 2000 + year if year < 50 else 1900 + year
        normalized = f"CA-{prefix}.{year:02d}-{month:02d}-{case_num:03d}"

        # Map to docket_type NOT sector!
        docket_type = DOCKET_TYPE_MAPPINGS.get('CA', {}).get(prefix)

        return ParsedDocket(
            raw=raw, state_code='CA', normalized_id=normalized,
            year=full_year, case_number=case_num, prefix=prefix,
            docket_type=docket_type  # NOT utility_sector!
        )

    # Compact format: A2407003
    match2 = re.match(r'([A-Z])(\d{2})(\d{2})(\d{3})', cleaned)
    if match2:
        prefix = match2.group(1)
        year = int(match2.group(2))
        month = int(match2.group(3))
        case_num = int(match2.group(4))
        full_year = 2000 + year if year < 50 else 1900 + year

        normalized = f"CA-{prefix}.{year:02d}-{month:02d}-{case_num:03d}"
        docket_type = DOCKET_TYPE_MAPPINGS.get('CA', {}).get(prefix)

        return ParsedDocket(
            raw=raw, state_code='CA', normalized_id=normalized,
            year=full_year, case_number=case_num, prefix=prefix,
            docket_type=docket_type
        )

    return ParsedDocket(raw=raw, state_code='CA', normalized_id=f"CA-{cleaned}")


def parse_new_york(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    New York format: YY-X-NNNN
    Example: 24-E-0314 (Year 2024, Electric, Case 314)
    Sector: YES (E, G, W, C, M)
    Type: NO
    """
    match = re.match(r'(\d{2})-?([A-Z])-?(\d{4})', cleaned)

    if match:
        year_2d = int(match.group(1))
        sector_code = match.group(2)
        case_num = int(match.group(3))

        full_year = 2000 + year_2d if year_2d < 50 else 1900 + year_2d
        sector = SECTOR_MAPPINGS.get('NY', {}).get(sector_code)

        normalized = f"NY-{year_2d:02d}-{sector_code}-{case_num:04d}"

        return ParsedDocket(
            raw=raw, state_code='NY', normalized_id=normalized,
            year=full_year, case_number=case_num, prefix=sector_code,
            utility_sector=sector
        )

    return ParsedDocket(raw=raw, state_code='NY', normalized_id=f"NY-{cleaned}")


def parse_washington(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    Washington format: XX-YYNNNN
    Example: UE-210223 (Electric Utility, Year 2021, Case 223)
    Sector: YES (UE, UG, UW, UT, TG, TR)
    Type: NO
    """
    match = re.match(r'([A-Z]{2})-?(\d{2})(\d{4})', cleaned)

    if match:
        sector_code = match.group(1)
        year_2d = int(match.group(2))
        case_num = int(match.group(3))

        full_year = 2000 + year_2d if year_2d < 50 else 1900 + year_2d
        sector = SECTOR_MAPPINGS.get('WA', {}).get(sector_code)

        normalized = f"WA-{sector_code}-{year_2d:02d}{case_num:04d}"

        return ParsedDocket(
            raw=raw, state_code='WA', normalized_id=normalized,
            year=full_year, case_number=case_num, prefix=sector_code,
            utility_sector=sector
        )

    return ParsedDocket(raw=raw, state_code='WA', normalized_id=f"WA-{cleaned}")


def parse_new_jersey(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    New Jersey format: XXYYMMNNNNN
    Example: ER25040190 (Electric Rate, 2025, April, Case 190)
    Sector: YES (first letter: E, G, W, A)
    Type: YES (second letter: R=Rate, O=Order)
    """
    match = re.match(r'([EGW])([RO])(\d{2})(\d{2})(\d+)', cleaned)

    if match:
        sector_letter = match.group(1)
        type_letter = match.group(2)
        year_2d = int(match.group(3))
        month = int(match.group(4))
        case_num = int(match.group(5))

        full_year = 2000 + year_2d if year_2d < 50 else 1900 + year_2d
        sector = SECTOR_MAPPINGS.get('NJ', {}).get(sector_letter)
        docket_type = DOCKET_TYPE_MAPPINGS.get('NJ', {}).get(type_letter)

        normalized = f"NJ-{sector_letter}{type_letter}{year_2d:02d}{month:02d}{case_num:05d}"

        return ParsedDocket(
            raw=raw, state_code='NJ', normalized_id=normalized,
            year=full_year, case_number=case_num,
            prefix=f"{sector_letter}{type_letter}",
            utility_sector=sector, docket_type=docket_type
        )

    # Try AO/AX format (Administrative)
    match2 = re.match(r'([A])([OX])(\d{2})(\d{2})(\d+)', cleaned)
    if match2:
        sector_letter = match2.group(1)
        type_letter = match2.group(2)
        year_2d = int(match2.group(3))
        month = int(match2.group(4))
        case_num = int(match2.group(5))

        full_year = 2000 + year_2d if year_2d < 50 else 1900 + year_2d

        return ParsedDocket(
            raw=raw, state_code='NJ',
            normalized_id=f"NJ-{sector_letter}{type_letter}{year_2d:02d}{month:02d}{case_num:05d}",
            year=full_year, case_number=case_num,
            prefix=f"{sector_letter}{type_letter}",
            utility_sector='other'
        )

    return ParsedDocket(raw=raw, state_code='NJ', normalized_id=f"NJ-{cleaned}")


def parse_colorado(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    Colorado format: YYX-NNNN[XX]
    Example: 21A-0625EG (Year 2021, Application, Case 625, Electric+Gas)
    Sector: Sometimes (suffix EG, E, G)
    Type: YES (A, AL, C, F, I, R, Q, M, etc.)
    """
    # Format with sector suffix: 21A-0625EG
    match = re.match(r'(\d{2})([A-Z]{1,2})-?(\d{4})([EG]{1,2})?', cleaned)

    if match:
        year_2d = int(match.group(1))
        type_code = match.group(2)
        case_num = int(match.group(3))
        sector_suffix = match.group(4)

        full_year = 2000 + year_2d if year_2d < 50 else 1900 + year_2d
        docket_type = DOCKET_TYPE_MAPPINGS.get('CO', {}).get(type_code)
        sector = SECTOR_MAPPINGS.get('CO', {}).get(sector_suffix) if sector_suffix else None

        normalized = f"CO-{year_2d:02d}{type_code}-{case_num:04d}"
        if sector_suffix:
            normalized += sector_suffix

        return ParsedDocket(
            raw=raw, state_code='CO', normalized_id=normalized,
            year=full_year, case_number=case_num,
            prefix=type_code, suffix=sector_suffix,
            utility_sector=sector, docket_type=docket_type
        )

    return ParsedDocket(raw=raw, state_code='CO', normalized_id=f"CO-{cleaned}")


def parse_pennsylvania(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    Pennsylvania format: X-YYYY-NNNNNNN
    Example: R-2025-3057164 (Rate case, 2025, Case 3057164)
    Sector: NO
    Type: YES (R=Rate, C=Complaint, M=Misc, A=Application)
    """
    match = re.match(r'([RCMA])-?(\d{4})-?(\d+)', cleaned)

    if match:
        type_code = match.group(1)
        year = int(match.group(2))
        case_num = int(match.group(3))

        docket_type = DOCKET_TYPE_MAPPINGS.get('PA', {}).get(type_code)
        normalized = f"PA-{type_code}-{year}-{case_num}"

        return ParsedDocket(
            raw=raw, state_code='PA', normalized_id=normalized,
            year=year, case_number=case_num, prefix=type_code,
            docket_type=docket_type
        )

    return ParsedDocket(raw=raw, state_code='PA', normalized_id=f"PA-{cleaned}")


def parse_south_carolina(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    South Carolina format: YYYY-NNN-X
    Example: 2023-189-E (Year 2023, Case 189, Electric)
    Sector: YES (E, G, W, C, T)
    Type: NO
    """
    match = re.match(r'(\d{4})-?(\d+)-?([EGWCTA])', cleaned)

    if match:
        year = int(match.group(1))
        case_num = int(match.group(2))
        sector_code = match.group(3)

        sector = SECTOR_MAPPINGS.get('SC', {}).get(sector_code)
        normalized = f"SC-{year}-{case_num:03d}-{sector_code}"

        return ParsedDocket(
            raw=raw, state_code='SC', normalized_id=normalized,
            year=year, case_number=case_num, suffix=sector_code,
            utility_sector=sector
        )

    return ParsedDocket(raw=raw, state_code='SC', normalized_id=f"SC-{cleaned}")


def parse_south_dakota(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    South Dakota format: XXYY-NNN
    Example: EL24-011 (Electric, 2024, Case 11)
    Sector: YES (EL, NG, TC, HP)
    Type: NO
    """
    match = re.match(r'([A-Z]{2})(\d{2})-?(\d+)', cleaned)

    if match:
        sector_code = match.group(1)
        year_2d = int(match.group(2))
        case_num = int(match.group(3))

        full_year = 2000 + year_2d if year_2d < 50 else 1900 + year_2d
        sector = SECTOR_MAPPINGS.get('SD', {}).get(sector_code)

        normalized = f"SD-{sector_code}{year_2d:02d}-{case_num:03d}"

        return ParsedDocket(
            raw=raw, state_code='SD', normalized_id=normalized,
            year=full_year, case_number=case_num, prefix=sector_code,
            utility_sector=sector
        )

    return ParsedDocket(raw=raw, state_code='SD', normalized_id=f"SD-{cleaned}")


def parse_oregon(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    Oregon format: XX NNN
    Example: UE 439 (Electric Utility, Case 439)
    Sector: YES (UE, UG, UW, UM)
    Type: Embedded in sector code (E=electric matters, M=misc)
    """
    match = re.match(r'([A-Z]{2})\s*(\d+)', cleaned)

    if match:
        sector_code = match.group(1)
        case_num = int(match.group(2))

        sector = SECTOR_MAPPINGS.get('OR', {}).get(sector_code)
        normalized = f"OR-{sector_code}-{case_num}"

        return ParsedDocket(
            raw=raw, state_code='OR', normalized_id=normalized,
            case_number=case_num, prefix=sector_code,
            utility_sector=sector
        )

    return ParsedDocket(raw=raw, state_code='OR', normalized_id=f"OR-{cleaned}")


def parse_north_carolina(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    North Carolina format: X-N,SUB NNN
    Example: E-2,SUB 1300 (Electric, Company 2, Subdocket 1300)
    Sector: YES (E, G, W)
    Type: NO
    Company-based: YES (the number after the letter is company ID)
    """
    match = re.match(r'([A-Z])-?(\d+),?\s*SUB\s*(\d+)', cleaned, re.IGNORECASE)

    if match:
        sector_code = match.group(1)
        company_num = int(match.group(2))
        sub_num = int(match.group(3))

        normalized = f"NC-{sector_code}-{company_num}-SUB-{sub_num}"
        sector = SECTOR_MAPPINGS.get('NC', {}).get(sector_code)

        return ParsedDocket(
            raw=raw, state_code='NC', normalized_id=normalized,
            case_number=sub_num, prefix=sector_code,
            utility_sector=sector,
            company_code=f"{sector_code}-{company_num}"
        )

    return ParsedDocket(raw=raw, state_code='NC', normalized_id=f"NC-{cleaned}")


def parse_georgia(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    Georgia format: NNNNN
    Example: 44280 (just sequential)
    Sector: NO (must be scraped)
    Type: NO (must be scraped)
    """
    match = re.match(r'(\d+)', cleaned)

    if match:
        case_num = int(match.group(1))
        return ParsedDocket(
            raw=raw, state_code='GA', normalized_id=f"GA-{case_num}",
            case_number=case_num
        )

    return ParsedDocket(raw=raw, state_code='GA', normalized_id=f"GA-{cleaned}")


def parse_texas(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """
    Texas format: NNNNN
    Example: 55599 (just sequential control number)
    Sector: NO (must be scraped from PDF)
    Type: NO (must be scraped)
    """
    match = re.match(r'(\d+)', cleaned)

    if match:
        case_num = int(match.group(1))
        return ParsedDocket(
            raw=raw, state_code='TX', normalized_id=f"TX-{case_num}",
            case_number=case_num
        )

    return ParsedDocket(raw=raw, state_code='TX', normalized_id=f"TX-{cleaned}")


def parse_generic(raw: str, cleaned: str, state_code: str) -> ParsedDocket:
    """Generic parser for states without specific format."""
    # Try to extract 4-digit year
    year_match = re.search(r'(19|20)(\d{2})', cleaned)
    year = int(year_match.group(0)) if year_match else None

    # Try to extract 2-digit year at start
    if not year:
        year_2d_match = re.match(r'(\d{2})-', cleaned)
        if year_2d_match:
            y = int(year_2d_match.group(1))
            year = 2000 + y if y < 50 else 1900 + y

    # Extract case number (last numeric sequence)
    num_matches = re.findall(r'(\d+)', cleaned)
    case_num = int(num_matches[-1]) if num_matches else None

    # Clean up normalized ID
    normalized = re.sub(r'[^\w\-]', '-', cleaned)
    normalized = re.sub(r'-+', '-', normalized).strip('-')

    return ParsedDocket(
        raw=raw,
        state_code=state_code,
        normalized_id=f"{state_code}-{normalized}",
        year=year,
        case_number=case_num
    )


# =============================================================================
# PARSER REGISTRY
# =============================================================================

STATE_PARSERS: Dict[str, Callable] = {
    'FL': parse_florida,
    'OH': parse_ohio,
    'CA': parse_california,
    'NY': parse_new_york,
    'WA': parse_washington,
    'NJ': parse_new_jersey,
    'CO': parse_colorado,
    'PA': parse_pennsylvania,
    'SC': parse_south_carolina,
    'SD': parse_south_dakota,
    'OR': parse_oregon,
    'NC': parse_north_carolina,
    'GA': parse_georgia,
    'TX': parse_texas,
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def normalize_for_matching(docket_id: str) -> str:
    """
    Normalize docket ID for fuzzy matching.
    Removes state prefix and standardizes format.
    """
    normalized = re.sub(r'^[A-Z]{2}-?', '', docket_id.upper())
    normalized = re.sub(r'[^\w\-]', '', normalized)
    normalized = re.sub(r'-+', '-', normalized)
    return normalized.strip('-')


def extract_year_from_docket(docket_id: str) -> Optional[int]:
    """Extract year from docket ID if present."""
    # 4-digit year
    match = re.search(r'(19|20)\d{2}', docket_id)
    if match:
        return int(match.group(0))

    # 2-digit year after dot (CA format)
    match = re.search(r'\.(\d{2})-', docket_id)
    if match:
        year = int(match.group(1))
        return 2000 + year if year < 50 else 1900 + year

    return None


def infer_sector_from_text(text: str) -> Optional[str]:
    """Infer sector from surrounding text context."""
    text_lower = text.lower()

    electric_keywords = ['electric', 'power', 'energy', 'kwh', 'megawatt', 'transmission', 'generation']
    gas_keywords = ['gas', 'natural gas', 'lng', 'pipeline', 'therm', 'mcf']
    water_keywords = ['water', 'wastewater', 'sewer', 'utility water', 'aqua']
    telecom_keywords = ['telecom', 'telephone', 'communications', 'broadband', 'wireless']

    for keyword in electric_keywords:
        if keyword in text_lower:
            return 'electric'
    for keyword in gas_keywords:
        if keyword in text_lower:
            return 'gas'
    for keyword in water_keywords:
        if keyword in text_lower:
            return 'water'
    for keyword in telecom_keywords:
        if keyword in text_lower:
            return 'telecom'

    return None


def get_parser_coverage() -> Dict[str, bool]:
    """Return which states have custom parsers vs generic."""
    all_states = [
        'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL',
        'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME',
        'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH',
        'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI',
        'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY'
    ]
    return {state: state in STATE_PARSERS for state in all_states}
