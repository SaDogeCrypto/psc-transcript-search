#!/usr/bin/env python3
"""
Backfill missing docket records from fl_documents and fl_case_events.

For each unique docket_number that matches proper format (YYYYNNNN-XX):
- If no fl_dockets record exists, create one
- Set utility_name from document filer if it's a known utility
- Set filed_date from earliest document filed_date
- Set sector_code from the docket suffix

Also normalizes existing dockets:
- If docket exists as "20250011" but documents have "20250011-EI", update to include suffix

Usage:
    # Preview what would be created (dry-run)
    python scripts/backfill_dockets_from_documents.py --dry-run

    # Actually create the missing dockets
    python scripts/backfill_dockets_from_documents.py --create

    # Show statistics only
    python scripts/backfill_dockets_from_documents.py --stats

    # Also normalize existing dockets (add missing suffixes)
    python scripts/backfill_dockets_from_documents.py --create --normalize
"""

import argparse
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
script_dir = Path(__file__).resolve().parent
src_dir = script_dir.parent / 'src'
sys.path.insert(0, str(src_dir))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import func, distinct
from florida.models import SessionLocal, FLDocket
from florida.models.document import FLDocument
from florida.models.sales import FLCaseEvent


# Valid docket number pattern: YYYYNNNN-XX (e.g., 20250011-EI)
VALID_DOCKET_PATTERN = re.compile(r'^(\d{4})(\d{4})-([A-Z]{2})$')

# Sector code descriptions
SECTOR_CODES = {
    'EI': ('Electric', 'Electric utility'),
    'EU': ('Electric', 'Electric utility'),
    'EM': ('Electric', 'Electric merger/acquisition'),
    'EC': ('Electric', 'Electric certificate'),
    'EQ': ('Electric', 'Electric CPCN'),
    'EG': ('Electric', 'Electric general'),
    'GU': ('Gas', 'Gas utility'),
    'GM': ('Gas', 'Gas merger/acquisition'),
    'WS': ('Water/Sewer', 'Water and sewer utility'),
    'WU': ('Water/Sewer', 'Water utility'),
    'SU': ('Water/Sewer', 'Sewer utility'),
    'TL': ('Telecom', 'Telecommunications'),
    'TX': ('Telecom', 'Telecommunications'),
    'OT': ('Other', 'Other/miscellaneous'),
    'AA': ('Administrative', 'Administrative action'),
    'RP': ('Rulemaking', 'Rulemaking proceeding'),
    'RR': ('Rulemaking', 'Rulemaking'),
    'CI': ('Complaint', 'Consumer complaint/investigation'),
    'CU': ('Complaint', 'Consumer utility complaint'),
    'PU': ('Pipeline', 'Pipeline utility'),
    'FO': ('Fuel', 'Fuel and purchased power'),
    'OG': ('Oil/Gas', 'Oil and gas'),
}

# Common utility name patterns for extraction
UTILITY_PATTERNS = [
    (r'Florida Power\s*&?\s*Light|FPL', 'Florida Power & Light Company'),
    (r'Duke Energy Florida|Duke Energy|DEF', 'Duke Energy Florida'),
    (r'Tampa Electric|TECO', 'Tampa Electric Company'),
    (r'Gulf Power', 'Gulf Power Company'),
    (r'Florida Public Utilities|FPUC', 'Florida Public Utilities Company'),
    (r'JEA', 'JEA'),
    (r'Orlando Utilities|OUC', 'Orlando Utilities Commission'),
    (r'Gainesville Regional|GRU', 'Gainesville Regional Utilities'),
    (r'Peoples Gas', 'Peoples Gas System'),
    (r'Florida City Gas|FCG', 'Florida City Gas'),
]


def extract_utility_name(text):
    """Extract standardized utility name from text."""
    if not text:
        return None
    for pattern, name in UTILITY_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return name
    return None


def get_all_docket_numbers(session):
    """
    Get all unique, valid docket numbers from fl_documents AND fl_case_events.

    Returns dict mapping docket_number -> {earliest_date, filers, doc_count, event_count}
    """
    docket_info = defaultdict(lambda: {
        'earliest_date': None,
        'filers': set(),
        'titles': [],
        'doc_count': 0,
        'event_count': 0
    })

    # Get docket numbers from documents
    docs = session.query(
        FLDocument.docket_number,
        FLDocument.filed_date,
        FLDocument.filer_name,
        FLDocument.title
    ).filter(
        FLDocument.docket_number.isnot(None)
    ).all()

    for docket_number, filed_date, filer_name, title in docs:
        # Only process valid format docket numbers
        if not VALID_DOCKET_PATTERN.match(docket_number):
            continue

        info = docket_info[docket_number]
        info['doc_count'] += 1

        if filed_date:
            if info['earliest_date'] is None or filed_date < info['earliest_date']:
                info['earliest_date'] = filed_date

        if filer_name:
            info['filers'].add(filer_name)

        if title:
            info['titles'].append(title)

    # Get docket numbers from case events
    events = session.query(
        FLCaseEvent.docket_number,
        FLCaseEvent.event_date,
        FLCaseEvent.who,
        FLCaseEvent.what
    ).filter(
        FLCaseEvent.docket_number.isnot(None)
    ).all()

    for docket_number, event_date, who, what in events:
        # Only process valid format docket numbers
        if not VALID_DOCKET_PATTERN.match(docket_number):
            continue

        info = docket_info[docket_number]
        info['event_count'] += 1

        if event_date:
            if info['earliest_date'] is None or event_date < info['earliest_date']:
                info['earliest_date'] = event_date

        if who:
            info['filers'].add(who)

        if what:
            info['titles'].append(what)

    return dict(docket_info)


def get_existing_dockets(session):
    """Get all existing docket numbers from fl_dockets."""
    dockets = session.query(FLDocket.docket_number).all()
    return {d[0] for d in dockets if d[0]}


def find_base_docket_matches(session, doc_dockets, existing_dockets):
    """
    Find dockets that exist with wrong format (missing suffix).

    Returns list of (old_docket_number, new_docket_number) tuples.
    """
    matches = []

    for doc_docket in doc_dockets:
        match = VALID_DOCKET_PATTERN.match(doc_docket)
        if match:
            year, seq, suffix = match.groups()
            base_number = f"{year}{seq}"  # e.g., "20250011"

            # Check if base exists but full doesn't
            if base_number in existing_dockets and doc_docket not in existing_dockets:
                matches.append((base_number, doc_docket))

    return matches


def create_docket_from_documents(docket_number, doc_info):
    """Create a new FLDocket record from document information."""
    match = VALID_DOCKET_PATTERN.match(docket_number)
    if not match:
        return None

    year, seq, sector_code = match.groups()
    year = int(year)
    sequence = int(seq)

    # Get sector info
    industry_type, case_type = SECTOR_CODES.get(sector_code, ('Unknown', 'Unknown'))

    # Try to extract utility name from filers
    utility_name = None
    for filer in doc_info['filers']:
        utility_name = extract_utility_name(filer)
        if utility_name:
            break

    # If no utility from filers, try titles
    if not utility_name:
        for title in doc_info['titles'][:5]:  # Check first 5 titles
            utility_name = extract_utility_name(title)
            if utility_name:
                break

    # Generate a title from the first document or use a default
    title = None
    if doc_info['titles']:
        # Find a non-order title if possible
        for t in doc_info['titles']:
            if t and not t.startswith('PSC-') and not t.startswith('ORDER'):
                title = t[:200]  # Truncate
                break

    return FLDocket(
        docket_number=docket_number,
        year=year,
        sequence=sequence,
        sector_code=sector_code,
        title=title,
        utility_name=utility_name,
        industry_type=industry_type,
        case_type=case_type,
        filed_date=doc_info['earliest_date'],
        status='open',  # Default to open since we don't know
        psc_docket_url=f"https://www.floridapsc.com/ClerkOffice/DocketFiling?docket={docket_number}",
        created_at=datetime.utcnow(),
    )


def print_stats(session):
    """Print statistics about docket coverage."""
    doc_dockets = get_all_docket_numbers(session)
    existing_dockets = get_existing_dockets(session)

    # Categorize
    missing = [d for d in doc_dockets if d not in existing_dockets]
    covered = [d for d in doc_dockets if d in existing_dockets]

    # Find base-number matches
    base_matches = find_base_docket_matches(session, doc_dockets.keys(), existing_dockets)

    print("\n" + "=" * 60)
    print("DOCKET COVERAGE STATISTICS")
    print("=" * 60)
    print(f"\nUnique docket numbers (valid format) from docs/events: {len(doc_dockets):,}")
    print(f"Existing docket records in fl_dockets: {len(existing_dockets):,}")
    print(f"\nCoverage:")
    print(f"  Dockets with fl_dockets record: {len(covered):,}")
    print(f"  Dockets MISSING fl_dockets record: {len(missing):,}")
    print(f"  Dockets with wrong format (base only): {len(base_matches):,}")

    if missing:
        print(f"\nSample of missing dockets:")
        for d in sorted(missing, reverse=True)[:15]:
            info = doc_dockets[d]
            print(f"  {d}: {info['doc_count']} docs, {info['event_count']} events, earliest: {info['earliest_date']}")

    if base_matches:
        print(f"\nDockets needing format correction:")
        for old, new in base_matches[:10]:
            print(f"  {old} -> {new}")


def main():
    parser = argparse.ArgumentParser(
        description='Backfill missing docket records from fl_documents'
    )

    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--dry-run', action='store_true',
                       help='Preview what would be created without making changes')
    action.add_argument('--create', action='store_true',
                       help='Actually create the missing docket records')
    action.add_argument('--stats', action='store_true',
                       help='Show statistics only')

    parser.add_argument('--normalize', action='store_true',
                       help='Also fix existing dockets with wrong format')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed output')
    parser.add_argument('--limit', type=int, default=None,
                       help='Limit number of dockets to create')

    args = parser.parse_args()

    session = SessionLocal()

    try:
        if args.stats:
            print_stats(session)
            return

        print("\n" + "=" * 60)
        print("DOCKET BACKFILL" + (" (DRY RUN)" if args.dry_run else ""))
        print("=" * 60)

        doc_dockets = get_all_docket_numbers(session)
        existing_dockets = get_existing_dockets(session)

        # Find missing dockets
        missing = [d for d in doc_dockets if d not in existing_dockets]
        print(f"\nFound {len(missing)} docket numbers in documents without fl_dockets record")

        # Apply limit if specified
        if args.limit:
            missing = missing[:args.limit]
            print(f"  (limited to {args.limit})")

        # Find dockets needing normalization
        base_matches = find_base_docket_matches(session, doc_dockets.keys(), existing_dockets)

        created_count = 0
        normalized_count = 0

        # Create missing dockets
        if args.create or args.dry_run:
            for docket_number in missing:
                doc_info = doc_dockets[docket_number]
                new_docket = create_docket_from_documents(docket_number, doc_info)

                if new_docket:
                    if args.verbose or args.dry_run:
                        print(f"  {'Would create' if args.dry_run else 'Creating'}: {docket_number}")
                        print(f"    Utility: {new_docket.utility_name or 'Unknown'}")
                        print(f"    Filed: {new_docket.filed_date}")
                        print(f"    Docs: {doc_info['doc_count']}")

                    if args.create:
                        session.add(new_docket)
                        created_count += 1

                        # Commit in batches
                        if created_count % 100 == 0:
                            session.commit()
                            print(f"  ... created {created_count} dockets")

        # Normalize existing dockets
        if args.normalize and base_matches:
            print(f"\nNormalizing {len(base_matches)} dockets with wrong format...")

            for old_number, new_number in base_matches:
                docket = session.query(FLDocket).filter(
                    FLDocket.docket_number == old_number
                ).first()

                if docket:
                    if args.verbose or args.dry_run:
                        print(f"  {'Would update' if args.dry_run else 'Updating'}: {old_number} -> {new_number}")

                    if args.create:
                        # Parse the new number for sector code
                        match = VALID_DOCKET_PATTERN.match(new_number)
                        if match:
                            _, _, sector_code = match.groups()
                            docket.docket_number = new_number
                            docket.sector_code = sector_code
                            industry_type, case_type = SECTOR_CODES.get(sector_code, ('Unknown', 'Unknown'))
                            docket.industry_type = industry_type
                            docket.case_type = case_type
                            normalized_count += 1

        if args.create:
            session.commit()
            print(f"\n✓ Created {created_count} new docket records")
            if args.normalize:
                print(f"✓ Normalized {normalized_count} existing docket records")
        else:
            print(f"\nDry run - no changes made")
            print(f"Would create: {len(missing)} dockets")
            if args.normalize:
                print(f"Would normalize: {len(base_matches)} dockets")
            print("Run with --create to actually make the changes")

    finally:
        session.close()


if __name__ == '__main__':
    main()
