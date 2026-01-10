#!/usr/bin/env python3
"""
Cleanup fake docket records created from order numbers.

The Thunderstone importer incorrectly created docket records from order numbers
(PSC-YYYY-NNNN-XXX-YY). These are not real dockets and need to be removed.

This script:
1. Identifies fake docket records (title like PSC-% or docket_number without suffix)
2. Checks if they have linked documents/hearings/events
3. Deletes records with no links, or reports those that need manual review

Usage:
    # Preview what would be deleted (dry-run)
    python scripts/cleanup_fake_dockets.py --dry-run

    # Actually delete the fake records
    python scripts/cleanup_fake_dockets.py --delete

    # Show statistics only
    python scripts/cleanup_fake_dockets.py --stats
"""

import argparse
import re
import sys
from pathlib import Path

# Add parent to path for imports
script_dir = Path(__file__).resolve().parent
src_dir = script_dir.parent / 'src'
sys.path.insert(0, str(src_dir))

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import func, text, and_, or_
from florida.models import SessionLocal, FLDocket
from florida.models.document import FLDocument
from florida.models.hearing import FLHearing
from florida.models.linking import FLHearingDocket
from florida.models.sales import FLCaseEvent


# Valid docket number pattern: YYYYNNNN-XX (e.g., 20250011-EI)
VALID_DOCKET_PATTERN = re.compile(r'^\d{8}-[A-Z]{2}$')


def get_fake_dockets(session):
    """
    Find docket records that are likely fake (created from order numbers).

    Criteria:
    - Title starts with 'PSC-' (order number as title)
    - Title starts with 'ORDER'
    - docket_number doesn't match valid pattern (missing sector suffix)
    """
    # Query for records with PSC-% or ORDER% title
    order_title_dockets = session.query(FLDocket).filter(
        or_(
            FLDocket.title.like('PSC-%'),
            FLDocket.title.like('ORDER%')
        )
    ).all()

    # Query for records with invalid docket_number format
    all_dockets = session.query(FLDocket).all()
    invalid_format_dockets = [
        d for d in all_dockets
        if d.docket_number and not VALID_DOCKET_PATTERN.match(d.docket_number)
        and d not in order_title_dockets  # Avoid duplicates
    ]

    return order_title_dockets + invalid_format_dockets


def check_docket_links(session, docket):
    """
    Check if a docket has any linked records that would be orphaned.

    Returns dict with counts of linked records.
    """
    doc_count = session.query(func.count(FLDocument.id)).filter(
        FLDocument.docket_number == docket.docket_number
    ).scalar() or 0

    # Check hearing links via junction table
    hearing_count = session.query(func.count(FLHearingDocket.id)).filter(
        FLHearingDocket.docket_id == docket.id
    ).scalar() or 0

    # Check events
    event_count = session.query(func.count(FLCaseEvent.id)).filter(
        FLCaseEvent.docket_number == docket.docket_number
    ).scalar() or 0

    return {
        'documents': doc_count,
        'hearings': hearing_count,
        'events': event_count,
        'total': doc_count + hearing_count + event_count
    }


def print_stats(session):
    """Print statistics about docket data quality."""
    total = session.query(func.count(FLDocket.id)).scalar() or 0

    # Count by title pattern
    psc_title = session.query(func.count(FLDocket.id)).filter(
        FLDocket.title.like('PSC-%')
    ).scalar() or 0

    order_title = session.query(func.count(FLDocket.id)).filter(
        FLDocket.title.like('ORDER%')
    ).scalar() or 0

    # Count by docket_number format
    all_dockets = session.query(FLDocket.docket_number).all()
    valid_format = sum(1 for d in all_dockets if d[0] and VALID_DOCKET_PATTERN.match(d[0]))
    invalid_format = len(all_dockets) - valid_format

    print("\n" + "=" * 60)
    print("FL_DOCKETS DATA QUALITY STATISTICS")
    print("=" * 60)
    print(f"\nTotal docket records: {total:,}")
    print(f"\nBy title pattern:")
    print(f"  Title starts with 'PSC-': {psc_title:,} (likely orders)")
    print(f"  Title starts with 'ORDER': {order_title:,} (likely orders)")
    print(f"  Other titles: {total - psc_title - order_title:,}")
    print(f"\nBy docket_number format:")
    print(f"  Valid format (YYYYNNNN-XX): {valid_format:,}")
    print(f"  Invalid format (missing suffix): {invalid_format:,}")

    # Sample of problematic records
    print("\nSample of problematic records:")
    problems = session.query(FLDocket).filter(
        or_(
            FLDocket.title.like('PSC-%'),
            FLDocket.title.like('ORDER%')
        )
    ).limit(10).all()

    for d in problems:
        print(f"  {d.docket_number}: {d.title[:50] if d.title else 'No title'}...")


def main():
    parser = argparse.ArgumentParser(
        description='Cleanup fake docket records created from order numbers'
    )

    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--dry-run', action='store_true',
                       help='Preview what would be deleted without making changes')
    action.add_argument('--delete', action='store_true',
                       help='Actually delete the fake docket records')
    action.add_argument('--stats', action='store_true',
                       help='Show statistics only')

    parser.add_argument('--force', action='store_true',
                       help='Delete even if there are linked records (cascades to events)')
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Show detailed output')

    args = parser.parse_args()

    session = SessionLocal()

    try:
        if args.stats:
            print_stats(session)
            return

        print("\n" + "=" * 60)
        print("FL_DOCKETS CLEANUP" + (" (DRY RUN)" if args.dry_run else ""))
        print("=" * 60)

        fake_dockets = get_fake_dockets(session)
        print(f"\nFound {len(fake_dockets)} potentially fake docket records")

        # Categorize by whether they have links
        safe_to_delete = []
        has_links = []

        for docket in fake_dockets:
            links = check_docket_links(session, docket)

            if links['total'] == 0:
                safe_to_delete.append(docket)
            else:
                has_links.append((docket, links))

        print(f"\n  Safe to delete (no linked records): {len(safe_to_delete)}")
        print(f"  Has linked records (needs review): {len(has_links)}")

        # Show details
        if args.verbose:
            print("\n--- Safe to delete ---")
            for d in safe_to_delete[:20]:
                print(f"  {d.docket_number}: {d.title[:60] if d.title else 'No title'}")
            if len(safe_to_delete) > 20:
                print(f"  ... and {len(safe_to_delete) - 20} more")

            print("\n--- Has linked records ---")
            for d, links in has_links[:10]:
                print(f"  {d.docket_number}: {links['documents']} docs, {links['hearings']} hearings, {links['events']} events")
                print(f"    Title: {d.title[:60] if d.title else 'No title'}")
            if len(has_links) > 10:
                print(f"  ... and {len(has_links) - 10} more")

        # Perform deletion
        if args.delete:
            deleted_count = 0

            # Delete safe records
            for docket in safe_to_delete:
                session.delete(docket)
                deleted_count += 1

            # Optionally delete records with links (force mode)
            if args.force and has_links:
                print(f"\n--force specified: also deleting {len(has_links)} records with links")
                for docket, links in has_links:
                    # Delete associated events first
                    if links['events'] > 0:
                        session.query(FLCaseEvent).filter(
                            FLCaseEvent.docket_number == docket.docket_number
                        ).delete()
                    # Delete hearing links
                    if links['hearings'] > 0:
                        session.query(FLHearingDocket).filter(
                            FLHearingDocket.docket_id == docket.id
                        ).delete()
                    session.delete(docket)
                    deleted_count += 1

            session.commit()
            print(f"\n✓ Deleted {deleted_count} fake docket records")

            if has_links and not args.force:
                print(f"\n⚠ {len(has_links)} records with links were NOT deleted.")
                print("  Use --force to delete them (will also delete linked events)")

        else:
            print(f"\nDry run - no changes made")
            print("Run with --delete to actually remove the records")

    finally:
        session.close()


if __name__ == '__main__':
    main()
