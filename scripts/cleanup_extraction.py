#!/usr/bin/env python3
"""
Cleanup and re-extract script for smart extraction pipeline.

Usage:
    python scripts/cleanup_extraction.py --hearing-id 1697
    python scripts/cleanup_extraction.py --state TX --reprocess
    python scripts/cleanup_extraction.py --all --reprocess
"""

import argparse
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def cleanup_hearing(db, hearing_id: int, reprocess: bool = False):
    """Clean up old extractions for a hearing and optionally reprocess."""
    from sqlalchemy import text
    from app.models.database import Hearing, Transcript, HearingDocket, Docket

    hearing = db.query(Hearing).filter(Hearing.id == hearing_id).first()
    if not hearing:
        logger.error(f"Hearing {hearing_id} not found")
        return

    state_code = hearing.state.code if hearing.state else None
    logger.info(f"Cleaning up hearing {hearing_id}: {hearing.title}")

    # 1. Remove old hearing_dockets links
    old_links = db.query(HearingDocket).filter(HearingDocket.hearing_id == hearing_id).all()
    logger.info(f"  Removing {len(old_links)} old hearing_docket links")
    for link in old_links:
        db.delete(link)

    # 2. Remove old extracted_dockets for this hearing
    result = db.execute(text(
        "DELETE FROM extracted_dockets WHERE hearing_id = :hid"
    ), {"hid": hearing_id})
    logger.info(f"  Removed extracted_dockets records")

    # 3. Clean up orphaned dockets (dockets with no hearing links)
    orphans = db.execute(text("""
        SELECT d.id, d.normalized_id FROM dockets d
        LEFT JOIN hearing_dockets hd ON d.id = hd.docket_id
        WHERE hd.hearing_id IS NULL
        AND d.confidence IN ('unverified', 'possible')
    """))
    orphan_ids = [r[0] for r in orphans.fetchall()]
    if orphan_ids:
        logger.info(f"  Found {len(orphan_ids)} orphaned dockets to clean")
        db.execute(text("DELETE FROM dockets WHERE id IN :ids"), {"ids": tuple(orphan_ids)})

    db.commit()

    # 4. Optionally reprocess with smart extraction
    if reprocess:
        transcript = db.query(Transcript).filter(Transcript.hearing_id == hearing_id).first()
        if transcript and state_code:
            logger.info(f"  Reprocessing with smart extraction...")
            from app.pipeline.smart_extraction import SmartExtractionPipeline

            pipeline = SmartExtractionPipeline(db)
            candidates = pipeline.process_transcript(
                text=transcript.full_text,
                state_code=state_code,
                hearing_id=hearing_id
            )
            counts = pipeline.store_candidates(candidates, hearing_id)
            logger.info(f"  Results: {counts}")
        else:
            logger.warning(f"  No transcript or state code - skipping reprocess")

    logger.info(f"  Done with hearing {hearing_id}")


def cleanup_state(db, state_code: str, reprocess: bool = False):
    """Clean up all hearings for a state."""
    from app.models.database import Hearing, State

    state = db.query(State).filter(State.code == state_code.upper()).first()
    if not state:
        logger.error(f"State {state_code} not found")
        return

    hearings = db.query(Hearing).filter(Hearing.state_id == state.id).all()
    logger.info(f"Found {len(hearings)} hearings for {state_code}")

    for hearing in hearings:
        cleanup_hearing(db, hearing.id, reprocess)


def main():
    parser = argparse.ArgumentParser(description="Cleanup extraction data")
    parser.add_argument("--hearing-id", type=int, help="Specific hearing ID to clean")
    parser.add_argument("--state", type=str, help="State code to clean (e.g., TX)")
    parser.add_argument("--all", action="store_true", help="Clean all hearings")
    parser.add_argument("--reprocess", action="store_true", help="Reprocess with smart extraction")

    args = parser.parse_args()

    from app.database import SessionLocal
    db = SessionLocal()

    try:
        if args.hearing_id:
            cleanup_hearing(db, args.hearing_id, args.reprocess)
        elif args.state:
            cleanup_state(db, args.state, args.reprocess)
        elif args.all:
            logger.error("--all not implemented yet (too dangerous)")
        else:
            parser.print_help()
    finally:
        db.close()


if __name__ == "__main__":
    main()
