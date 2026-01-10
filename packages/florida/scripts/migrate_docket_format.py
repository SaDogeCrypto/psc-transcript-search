#!/usr/bin/env python3
"""
Migrate docket_number format from YYYYNNNN to YYYYNNNN-XX.

This script:
1. Finds old-format dockets (YYYYNNNN without suffix)
2. Looks up the correct sector code from the ClerkOffice API
3. Updates the docket_number to include the suffix
4. Also updates fl_documents and fl_hearings that reference the old format

Usage:
    # Preview changes
    python scripts/migrate_docket_format.py --dry-run

    # Apply changes
    python scripts/migrate_docket_format.py --migrate
"""

import argparse
import sys
import re
from pathlib import Path
from collections import defaultdict

# Add parent to path for imports
script_dir = Path(__file__).resolve().parent
src_dir = script_dir.parent / 'src'
sys.path.insert(0, str(src_dir))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from florida.models import SessionLocal, FLDocket
from florida.models.document import FLDocument
from florida.models.hearing import FLHearing
from florida.scrapers.clerkoffice import FloridaClerkOfficeScraper


def get_old_format_dockets(session):
    """Get all dockets without sector suffix."""
    result = session.execute(text("""
        SELECT id, docket_number, title, sector_code, year, sequence
        FROM fl_dockets
        WHERE docket_number ~ '^[0-9]{8}$'
        ORDER BY docket_number DESC
    """))
    return list(result)


def get_new_format_dockets(session):
    """Get all dockets with proper format to find duplicates."""
    result = session.execute(text("""
        SELECT docket_number
        FROM fl_dockets
        WHERE docket_number ~ '^[0-9]{8}-[A-Z]{2}$'
    """))
    return {row.docket_number for row in result}


def lookup_sector_code(scraper, base_docket):
    """Look up sector code from ClerkOffice API."""
    try:
        # Search for the docket
        results = scraper.client.search_dockets(base_docket)
        if results:
            for r in results:
                if isinstance(r, dict):
                    doc_type = r.get('documentType')
                    if doc_type and len(doc_type) == 2:
                        return doc_type

        # Try getting details
        details = scraper.client.get_docket_details(base_docket)
        if details:
            doc_type = details.get('documentType')
            if doc_type:
                return doc_type
    except Exception as e:
        pass
    return None


def migrate_docket(session, old_docket, new_docket_number, dry_run=True):
    """
    Migrate a single docket to new format.

    Strategy: Create new docket record, migrate references, delete old docket.
    This avoids FK constraint issues since we never update the PK.
    """
    old_number = old_docket.docket_number
    old_id = old_docket.id

    if dry_run:
        print(f"  Would update: {old_number} -> {new_docket_number}")
        return True

    sector_code = new_docket_number.split('-')[1] if '-' in new_docket_number else None

    # Step 1: Create new docket record with new format (copy data from old)
    session.execute(text("""
        INSERT INTO fl_dockets (
            docket_number, year, sequence, sector_code, title, utility_name,
            status, case_type, industry_type, filed_date, closed_date,
            psc_docket_url, created_at
        )
        SELECT
            :new_number, year, sequence, :sector_code, title, utility_name,
            status, case_type, industry_type, filed_date, closed_date,
            psc_docket_url, created_at
        FROM fl_dockets
        WHERE id = :old_id
    """), {'new_number': new_docket_number, 'sector_code': sector_code, 'old_id': old_id})

    # Step 2: Update referencing documents to new docket number
    doc_count = session.execute(text("""
        UPDATE fl_documents
        SET docket_number = :new_number
        WHERE docket_number = :old_number
    """), {'new_number': new_docket_number, 'old_number': old_number}).rowcount

    # Step 3: Update referencing hearings
    hearing_count = session.execute(text("""
        UPDATE fl_hearings
        SET docket_number = :new_number
        WHERE docket_number = :old_number
    """), {'new_number': new_docket_number, 'old_number': old_number}).rowcount

    # Step 4: Update case events
    event_count = session.execute(text("""
        UPDATE fl_case_events
        SET docket_number = :new_number
        WHERE docket_number = :old_number
    """), {'new_number': new_docket_number, 'old_number': old_number}).rowcount

    # Step 5: Delete old docket record
    session.execute(text("""
        DELETE FROM fl_dockets WHERE id = :old_id
    """), {'old_id': old_id})

    print(f"  Updated: {old_number} -> {new_docket_number} (docs:{doc_count}, hearings:{hearing_count}, events:{event_count})")
    return True


def merge_duplicate(session, old_docket, existing_new_number, dry_run=True):
    """Merge old docket into existing new-format docket."""
    old_number = old_docket.docket_number
    old_id = old_docket.id

    # Get the new docket's id
    result = session.execute(text("""
        SELECT id FROM fl_dockets WHERE docket_number = :dn
    """), {'dn': existing_new_number})
    new_id = result.scalar()

    if dry_run:
        print(f"  Would merge: {old_number} (id:{old_id}) into {existing_new_number} (id:{new_id})")
        return True

    # Point documents to new docket
    doc_count = session.execute(text("""
        UPDATE fl_documents
        SET docket_number = :new_number
        WHERE docket_number = :old_number
    """), {'new_number': existing_new_number, 'old_number': old_number}).rowcount

    # Point hearings to new docket
    hearing_count = session.execute(text("""
        UPDATE fl_hearings
        SET docket_number = :new_number
        WHERE docket_number = :old_number
    """), {'new_number': existing_new_number, 'old_number': old_number}).rowcount

    # Point case events to new docket
    event_count = session.execute(text("""
        UPDATE fl_case_events
        SET docket_number = :new_number
        WHERE docket_number = :old_number
    """), {'new_number': existing_new_number, 'old_number': old_number}).rowcount

    # Copy title if new one is empty
    session.execute(text("""
        UPDATE fl_dockets
        SET title = COALESCE(title, :old_title),
            utility_name = COALESCE(utility_name, :old_utility)
        WHERE docket_number = :new_number
          AND (title IS NULL OR title = '')
    """), {
        'new_number': existing_new_number,
        'old_title': old_docket.title,
        'old_utility': None  # Would need to fetch
    })

    # Delete the old docket
    session.execute(text("""
        DELETE FROM fl_dockets WHERE id = :id
    """), {'id': old_id})

    print(f"  Merged: {old_number} into {existing_new_number} (docs:{doc_count}, hearings:{hearing_count}, events:{event_count})")
    return True


def main():
    parser = argparse.ArgumentParser(description='Migrate docket format')
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--dry-run', action='store_true', help='Preview changes')
    action.add_argument('--migrate', action='store_true', help='Apply changes')
    parser.add_argument('--limit', type=int, default=None, help='Limit dockets to process')
    parser.add_argument('--skip-api', action='store_true', help='Skip API lookups, use existing sector_code')

    args = parser.parse_args()

    session = SessionLocal()
    scraper = FloridaClerkOfficeScraper() if not args.skip_api else None

    try:
        print("=" * 60)
        print("DOCKET FORMAT MIGRATION" + (" (DRY RUN)" if args.dry_run else ""))
        print("=" * 60)

        # Get old format dockets
        old_dockets = get_old_format_dockets(session)
        print(f"\nFound {len(old_dockets)} old-format dockets (YYYYNNNN)")

        # Get existing new format dockets (to detect duplicates)
        new_format_set = get_new_format_dockets(session)
        print(f"Found {len(new_format_set)} new-format dockets (YYYYNNNN-XX)")

        # Apply limit
        if args.limit:
            old_dockets = old_dockets[:args.limit]
            print(f"Processing first {args.limit}")

        # Track statistics
        stats = {
            'updated': 0,
            'merged': 0,
            'skipped_no_sector': 0,
            'errors': 0,
        }

        # Process each old docket
        print("\nProcessing...")
        for old_docket in old_dockets:
            base_number = old_docket.docket_number

            # First check if a new-format version already exists in DB
            # This handles duplicates even without knowing the sector code
            existing_match = None
            for new_num in new_format_set:
                if new_num.startswith(base_number + '-'):
                    existing_match = new_num
                    break

            if existing_match:
                # Merge into existing new-format docket
                try:
                    merge_duplicate(session, old_docket, existing_match, dry_run=args.dry_run)
                    stats['merged'] += 1
                except Exception as e:
                    print(f"  Error merging {base_number}: {e}")
                    stats['errors'] += 1
                    session.rollback()  # Reset transaction state
                continue

            # Determine sector code for non-duplicate cases
            sector_code = old_docket.sector_code
            if not sector_code and scraper:
                sector_code = lookup_sector_code(scraper, base_number)

            if not sector_code:
                # Skip if no sector code available
                if args.dry_run:
                    print(f"  Skip: {base_number} (no sector code)")
                stats['skipped_no_sector'] += 1
                continue

            new_number = f"{base_number}-{sector_code}"

            # Check if new format already exists (shouldn't happen now but just in case)
            if new_number in new_format_set:
                # Merge into existing
                try:
                    merge_duplicate(session, old_docket, new_number, dry_run=args.dry_run)
                    stats['merged'] += 1
                except Exception as e:
                    print(f"  Error merging {base_number}: {e}")
                    stats['errors'] += 1
                    session.rollback()
            else:
                # Update to new format
                try:
                    migrate_docket(session, old_docket, new_number, dry_run=args.dry_run)
                    stats['updated'] += 1
                    new_format_set.add(new_number)  # Track to avoid duplicates
                except Exception as e:
                    print(f"  Error updating {base_number}: {e}")
                    stats['errors'] += 1
                    session.rollback()

            # Commit in batches
            if not args.dry_run and (stats['updated'] + stats['merged']) % 100 == 0:
                session.commit()

        if not args.dry_run:
            session.commit()

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Updated: {stats['updated']}")
        print(f"Merged: {stats['merged']}")
        print(f"Skipped (no sector): {stats['skipped_no_sector']}")
        print(f"Errors: {stats['errors']}")

        if args.dry_run:
            print("\nThis was a dry run. Use --migrate to apply changes.")

    finally:
        session.close()


if __name__ == '__main__':
    main()
