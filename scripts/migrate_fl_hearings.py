#!/usr/bin/env python3
"""
Migrate Florida hearings from legacy unified schema to new per-state schema.

This script:
1. Queries FL hearings from the legacy database
2. Maps them to the new fl_hearings table
3. Migrates transcript segments to fl_transcript_segments
4. Optionally migrates analyses to fl_analyses

Environment variables:
- DATABASE_URL: Legacy database connection string
- FL_DATABASE_URL: Florida database connection string (defaults to DATABASE_URL if same DB)

Usage:
    python scripts/migrate_fl_hearings.py [--dry-run] [--limit N]
"""

import os
import sys
import argparse
import logging
from datetime import datetime
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_legacy_session():
    """Get session for legacy database."""
    url = os.getenv("DATABASE_URL", "sqlite:///data/psc_dev.db")
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    return Session()


def get_florida_session():
    """Get session for Florida database."""
    # Use FL_DATABASE_URL if set, otherwise fall back to DATABASE_URL
    url = os.getenv("FL_DATABASE_URL") or os.getenv("DATABASE_URL", "postgresql://localhost/psc_florida")
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    return Session()


def get_fl_state_id(legacy_db) -> Optional[int]:
    """Get the state ID for Florida from legacy database."""
    result = legacy_db.execute(text("SELECT id FROM states WHERE code = 'FL'")).fetchone()
    return result[0] if result else None


def migrate_hearings(
    legacy_db,
    fl_db,
    dry_run: bool = False,
    limit: Optional[int] = None
) -> dict:
    """
    Migrate Florida hearings from legacy to new schema.

    Returns stats about the migration.
    """
    stats = {
        'hearings_found': 0,
        'hearings_migrated': 0,
        'segments_migrated': 0,
        'analyses_migrated': 0,
        'skipped': 0,
        'errors': [],
    }

    # Get FL state ID
    fl_state_id = get_fl_state_id(legacy_db)
    if not fl_state_id:
        logger.error("Florida state not found in legacy database")
        return stats

    logger.info(f"Found Florida state_id: {fl_state_id}")

    # Query FL hearings
    query = """
        SELECT
            h.id,
            h.title,
            h.description,
            h.hearing_date,
            h.hearing_type,
            h.utility_name,
            h.docket_numbers,
            h.source_url,
            h.video_url,
            h.duration_seconds,
            h.status,
            h.external_id,
            h.sector,
            h.processing_cost_usd,
            h.created_at
        FROM hearings h
        WHERE h.state_id = :state_id
        ORDER BY h.hearing_date DESC
    """
    if limit:
        query += f" LIMIT {limit}"

    hearings = legacy_db.execute(text(query), {"state_id": fl_state_id}).fetchall()
    stats['hearings_found'] = len(hearings)

    logger.info(f"Found {len(hearings)} Florida hearings to migrate")

    hearing_id_map = {}  # Map old ID to new ID

    for h in hearings:
        try:
            # Extract first docket number if available
            docket_number = None
            if h.docket_numbers:
                docket_list = h.docket_numbers if isinstance(h.docket_numbers, list) else []
                if docket_list:
                    docket_number = docket_list[0]

            # Determine transcript status
            transcript_status = 'pending'
            if h.status == 'complete' or h.status == 'analyzed':
                transcript_status = 'transcribed'
            elif h.status == 'transcribed':
                transcript_status = 'transcribed'
            elif h.status == 'downloaded':
                transcript_status = 'downloaded'

            if dry_run:
                logger.info(f"  [DRY RUN] Would migrate hearing {h.id}: {h.title[:50]}...")
                hearing_id_map[h.id] = h.id  # Use same ID for dry run
            else:
                # Check if already migrated (by external_id or source_url)
                existing = fl_db.execute(text("""
                    SELECT id FROM fl_hearings
                    WHERE external_id = :ext_id OR source_url = :url
                """), {"ext_id": h.external_id, "url": h.source_url}).fetchone()

                if existing:
                    logger.debug(f"  Skipping hearing {h.id} - already migrated as {existing[0]}")
                    hearing_id_map[h.id] = existing[0]
                    stats['skipped'] += 1
                    continue

                # Insert into fl_hearings
                result = fl_db.execute(text("""
                    INSERT INTO fl_hearings (
                        docket_number, hearing_date, hearing_type, location, title,
                        transcript_url, transcript_status, source_type, source_url,
                        external_id, duration_seconds, whisper_model,
                        processing_cost_usd, created_at
                    ) VALUES (
                        :docket_number, :hearing_date, :hearing_type, NULL, :title,
                        NULL, :transcript_status, 'youtube', :source_url,
                        :external_id, :duration_seconds, 'whisper-1',
                        :processing_cost, :created_at
                    )
                    RETURNING id
                """), {
                    "docket_number": docket_number,
                    "hearing_date": h.hearing_date,
                    "hearing_type": h.hearing_type,
                    "title": h.title,
                    "transcript_status": transcript_status,
                    "source_url": h.video_url or h.source_url,
                    "external_id": h.external_id,
                    "duration_seconds": h.duration_seconds,
                    "processing_cost": h.processing_cost_usd or 0,
                    "created_at": h.created_at or datetime.utcnow(),
                })

                new_id = result.fetchone()[0]
                hearing_id_map[h.id] = new_id
                stats['hearings_migrated'] += 1
                logger.info(f"  Migrated hearing {h.id} -> {new_id}: {h.title[:50]}...")

        except Exception as e:
            logger.error(f"  Error migrating hearing {h.id}: {e}")
            stats['errors'].append(f"Hearing {h.id}: {e}")

    # Migrate segments for migrated hearings
    if hearing_id_map:
        logger.info(f"Migrating segments for {len(hearing_id_map)} hearings...")

        for old_id, new_id in hearing_id_map.items():
            try:
                segments = legacy_db.execute(text("""
                    SELECT
                        segment_index, start_time, end_time, text, speaker, speaker_role
                    FROM segments
                    WHERE hearing_id = :hearing_id
                    ORDER BY segment_index
                """), {"hearing_id": old_id}).fetchall()

                if not segments:
                    continue

                for seg in segments:
                    if dry_run:
                        stats['segments_migrated'] += 1
                        continue

                    fl_db.execute(text("""
                        INSERT INTO fl_transcript_segments (
                            hearing_id, segment_index, start_time, end_time,
                            speaker_label, speaker_name, speaker_role, text
                        ) VALUES (
                            :hearing_id, :segment_index, :start_time, :end_time,
                            :speaker_label, :speaker_name, :speaker_role, :text
                        )
                    """), {
                        "hearing_id": new_id,
                        "segment_index": seg.segment_index,
                        "start_time": seg.start_time,
                        "end_time": seg.end_time,
                        "speaker_label": seg.speaker,
                        "speaker_name": seg.speaker,  # Same as label initially
                        "speaker_role": seg.speaker_role,
                        "text": seg.text,
                    })
                    stats['segments_migrated'] += 1

            except Exception as e:
                logger.error(f"  Error migrating segments for hearing {old_id}: {e}")
                stats['errors'].append(f"Segments for hearing {old_id}: {e}")

    # Migrate analyses (optional)
    logger.info("Migrating analyses...")
    for old_id, new_id in hearing_id_map.items():
        try:
            analysis = legacy_db.execute(text("""
                SELECT
                    summary, one_sentence_summary, hearing_type, utility_name,
                    participants_json, issues_json, commitments_json,
                    vulnerabilities_json, commissioner_concerns_json,
                    commissioner_mood, public_comments, public_sentiment,
                    likely_outcome, outcome_confidence, risk_factors_json,
                    action_items_json, quotes_json, model, cost_usd
                FROM analyses
                WHERE hearing_id = :hearing_id
            """), {"hearing_id": old_id}).fetchone()

            if not analysis:
                continue

            if dry_run:
                stats['analyses_migrated'] += 1
                continue

            # Check if already exists
            existing = fl_db.execute(text("""
                SELECT id FROM fl_analyses WHERE hearing_id = :hid
            """), {"hid": new_id}).fetchone()

            if existing:
                continue

            fl_db.execute(text("""
                INSERT INTO fl_analyses (
                    hearing_id, summary, one_sentence_summary, hearing_type, utility_name,
                    participants_json, issues_json, commitments_json,
                    vulnerabilities_json, commissioner_concerns_json,
                    commissioner_mood, public_comments, public_sentiment,
                    likely_outcome, outcome_confidence, risk_factors_json,
                    action_items_json, quotes_json, model, cost_usd
                ) VALUES (
                    :hearing_id, :summary, :one_sentence_summary, :hearing_type, :utility_name,
                    :participants_json, :issues_json, :commitments_json,
                    :vulnerabilities_json, :commissioner_concerns_json,
                    :commissioner_mood, :public_comments, :public_sentiment,
                    :likely_outcome, :outcome_confidence, :risk_factors_json,
                    :action_items_json, :quotes_json, :model, :cost_usd
                )
            """), {
                "hearing_id": new_id,
                "summary": analysis.summary,
                "one_sentence_summary": analysis.one_sentence_summary,
                "hearing_type": analysis.hearing_type,
                "utility_name": analysis.utility_name,
                "participants_json": analysis.participants_json,
                "issues_json": analysis.issues_json,
                "commitments_json": analysis.commitments_json,
                "vulnerabilities_json": analysis.vulnerabilities_json,
                "commissioner_concerns_json": analysis.commissioner_concerns_json,
                "commissioner_mood": analysis.commissioner_mood,
                "public_comments": analysis.public_comments,
                "public_sentiment": analysis.public_sentiment,
                "likely_outcome": analysis.likely_outcome,
                "outcome_confidence": analysis.outcome_confidence,
                "risk_factors_json": analysis.risk_factors_json,
                "action_items_json": analysis.action_items_json,
                "quotes_json": analysis.quotes_json,
                "model": analysis.model,
                "cost_usd": analysis.cost_usd,
            })
            stats['analyses_migrated'] += 1

        except Exception as e:
            logger.error(f"  Error migrating analysis for hearing {old_id}: {e}")
            stats['errors'].append(f"Analysis for hearing {old_id}: {e}")

    if not dry_run:
        fl_db.commit()
        logger.info("Committed changes to Florida database")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Migrate Florida hearings to new schema")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually write to database")
    parser.add_argument("--limit", type=int, help="Limit number of hearings to migrate")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Florida Hearing Migration")
    logger.info("=" * 60)

    if args.dry_run:
        logger.info("DRY RUN MODE - no changes will be made")

    legacy_db = get_legacy_session()
    fl_db = get_florida_session()

    try:
        stats = migrate_hearings(
            legacy_db,
            fl_db,
            dry_run=args.dry_run,
            limit=args.limit,
        )

        logger.info("")
        logger.info("=" * 60)
        logger.info("Migration Complete")
        logger.info("=" * 60)
        logger.info(f"Hearings found:    {stats['hearings_found']}")
        logger.info(f"Hearings migrated: {stats['hearings_migrated']}")
        logger.info(f"Hearings skipped:  {stats['skipped']}")
        logger.info(f"Segments migrated: {stats['segments_migrated']}")
        logger.info(f"Analyses migrated: {stats['analyses_migrated']}")

        if stats['errors']:
            logger.info(f"Errors:            {len(stats['errors'])}")
            for err in stats['errors'][:10]:
                logger.error(f"  - {err}")

    finally:
        legacy_db.close()
        fl_db.close()


if __name__ == "__main__":
    main()
