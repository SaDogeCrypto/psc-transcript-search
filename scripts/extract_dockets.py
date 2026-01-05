#!/usr/bin/env python3
"""
CanaryScope Docket Extraction Pipeline

Extracts docket identifiers from hearing transcripts and stores them in the database.
Triggers notifications to users watching the extracted dockets.

Usage:
    python scripts/extract_dockets.py --hearing-id 123
    python scripts/extract_dockets.py --all-new
    python scripts/extract_dockets.py --reprocess-all
"""
import asyncio
import argparse
import json
import logging
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI
from sqlalchemy import text
from app.database import SessionLocal
from app.services.notifications import notify_watchlist_users

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

client = OpenAI()

EXTRACTION_PROMPT = """Analyze this transcript from a Public Service Commission hearing and extract all official proceeding identifiers.

Look for:
- Docket numbers (e.g., "Docket 44160", "Docket No. 2024-0034")
- Case numbers (e.g., "Case 24-001")
- Proceeding numbers (e.g., "A.24-01-001", "ER24-1234")
- Application numbers
- Any other official reference ID used to track this matter

For each identifier found, extract:
1. raw_text: The exact text as it appears
2. normalized_id: Clean ID with state prefix (e.g., "GA-44160", "CA-A2401001")
3. docket_type: What kind of proceeding (rate_case, irp, complaint, rulemaking, certificate, tariff, other)
4. company: Company involved if mentioned
5. context_summary: 1-2 sentence summary of what was discussed about this docket

Return JSON format:
{{
  "identifiers": [
    {{
      "raw_text": "Docket Number 44160",
      "normalized_id": "GA-44160",
      "docket_type": "rate_case",
      "company": "Georgia Power",
      "context_summary": "Discussion of base rate increase request and ROE testimony"
    }}
  ],
  "no_identifiers_found": false
}}

STATE: {state}
TRANSCRIPT:
{transcript}
"""


def extract_dockets_from_text(transcript_text: str, state_code: str) -> dict:
    """Extract docket identifiers from transcript text using GPT-4."""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=2000,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "user",
                    "content": EXTRACTION_PROMPT.format(
                        state=state_code,
                        transcript=transcript_text[:20000]  # Limit context
                    )
                }
            ]
        )

        result = json.loads(response.choices[0].message.content)
        return result

    except Exception as e:
        logger.error(f"Extraction failed: {e}")
        return {"identifiers": [], "error": str(e)}


def get_or_create_docket(db, state_id: int, state_code: str, identifier: dict) -> int:
    """Get existing docket or create new one. Returns docket ID."""
    normalized_id = identifier["normalized_id"]

    # Check if docket exists
    existing = db.execute(
        text("SELECT id FROM dockets WHERE normalized_id = :nid"),
        {"nid": normalized_id}
    ).fetchone()

    if existing:
        # Update mention count
        db.execute(
            text("""
                UPDATE dockets
                SET mention_count = mention_count + 1,
                    last_mentioned_at = NOW(),
                    updated_at = NOW()
                WHERE id = :id
            """),
            {"id": existing.id}
        )
        db.commit()
        return existing.id

    # Create new docket
    result = db.execute(
        text("""
            INSERT INTO dockets (
                state_id, docket_number, normalized_id, docket_type,
                company, status, first_seen_at, last_mentioned_at,
                mention_count, created_at, updated_at
            ) VALUES (
                :state_id, :docket_number, :normalized_id, :docket_type,
                :company, 'open', NOW(), NOW(), 1, NOW(), NOW()
            )
            RETURNING id
        """),
        {
            "state_id": state_id,
            "docket_number": identifier.get("raw_text", normalized_id),
            "normalized_id": normalized_id,
            "docket_type": identifier.get("docket_type", "other"),
            "company": identifier.get("company"),
        }
    )
    db.commit()

    new_id = result.fetchone().id
    logger.info(f"Created new docket: {normalized_id} (ID: {new_id})")
    return new_id


def link_hearing_to_docket(db, hearing_id: int, docket_id: int, summary: str) -> bool:
    """Create hearing-docket link if it doesn't exist. Returns True if new link created."""
    # Check if link exists
    existing = db.execute(
        text("""
            SELECT 1 FROM hearing_dockets
            WHERE hearing_id = :hid AND docket_id = :did
        """),
        {"hid": hearing_id, "did": docket_id}
    ).fetchone()

    if existing:
        return False

    # Create link
    db.execute(
        text("""
            INSERT INTO hearing_dockets (hearing_id, docket_id, mention_summary, created_at)
            VALUES (:hid, :did, :summary, NOW())
        """),
        {"hid": hearing_id, "did": docket_id, "summary": summary}
    )
    db.commit()
    return True


async def process_hearing(db, hearing_id: int, notify: bool = True) -> dict:
    """Process a single hearing for docket extraction."""
    # Get hearing info
    hearing = db.execute(
        text("""
            SELECT h.id, h.title, h.state_id, s.code as state_code, s.name as state_name
            FROM hearings h
            JOIN states s ON s.id = h.state_id
            WHERE h.id = :id
        """),
        {"id": hearing_id}
    ).fetchone()

    if not hearing:
        logger.error(f"Hearing {hearing_id} not found")
        return {"error": "Hearing not found"}

    # Get transcript text
    transcript = db.execute(
        text("""
            SELECT full_text FROM transcripts WHERE hearing_id = :id
        """),
        {"id": hearing_id}
    ).fetchone()

    if not transcript or not transcript.full_text:
        # Try reconstructing from segments
        segments = db.execute(
            text("""
                SELECT text FROM segments
                WHERE hearing_id = :id
                ORDER BY segment_index
            """),
            {"id": hearing_id}
        ).fetchall()

        if not segments:
            logger.warning(f"No transcript for hearing {hearing_id}")
            return {"error": "No transcript available"}

        transcript_text = " ".join([s.text for s in segments if s.text])
    else:
        transcript_text = transcript.full_text

    logger.info(f"Processing hearing {hearing_id}: {hearing.title[:50]}...")

    # Extract dockets
    result = extract_dockets_from_text(transcript_text, hearing.state_code)

    if result.get("error"):
        return result

    identifiers = result.get("identifiers", [])
    if not identifiers:
        logger.info(f"No dockets found in hearing {hearing_id}")
        return {"hearing_id": hearing_id, "dockets_found": 0}

    # Process each identifier
    new_links = []
    for ident in identifiers:
        # Ensure normalized_id has state prefix
        normalized_id = ident["normalized_id"]
        if not normalized_id.startswith(hearing.state_code):
            normalized_id = f"{hearing.state_code}-{normalized_id}"
            ident["normalized_id"] = normalized_id

        # Get or create docket
        docket_id = get_or_create_docket(db, hearing.state_id, hearing.state_code, ident)

        # Link to hearing
        is_new = link_hearing_to_docket(
            db, hearing_id, docket_id,
            ident.get("context_summary", "Mentioned in hearing")
        )

        if is_new:
            new_links.append({
                "docket_id": docket_id,
                "normalized_id": normalized_id,
                "summary": ident.get("context_summary")
            })

    # Send notifications for new links
    if notify and new_links:
        for link in new_links:
            try:
                count = await notify_watchlist_users(
                    db,
                    docket_id=link["docket_id"],
                    hearing_id=hearing_id,
                    mention_summary=link["summary"]
                )
                if count > 0:
                    logger.info(f"Notified {count} users about {link['normalized_id']}")
            except Exception as e:
                logger.error(f"Notification error: {e}")

    logger.info(f"Hearing {hearing_id}: Found {len(identifiers)} dockets, {len(new_links)} new links")

    return {
        "hearing_id": hearing_id,
        "dockets_found": len(identifiers),
        "new_links": len(new_links),
        "dockets": [i["normalized_id"] for i in identifiers]
    }


async def process_all_new_hearings(db, notify: bool = True) -> dict:
    """Process all hearings that haven't been processed for dockets yet."""
    # Find hearings with transcripts but no docket links
    hearings = db.execute(
        text("""
            SELECT DISTINCT h.id
            FROM hearings h
            JOIN transcripts t ON t.hearing_id = h.id
            WHERE NOT EXISTS (
                SELECT 1 FROM hearing_dockets hd WHERE hd.hearing_id = h.id
            )
            ORDER BY h.created_at DESC
        """)
    ).fetchall()

    logger.info(f"Found {len(hearings)} hearings to process")

    results = []
    for (hearing_id,) in hearings:
        result = await process_hearing(db, hearing_id, notify)
        results.append(result)

    total_dockets = sum(r.get("dockets_found", 0) for r in results)
    total_links = sum(r.get("new_links", 0) for r in results)

    return {
        "hearings_processed": len(results),
        "total_dockets_found": total_dockets,
        "total_new_links": total_links,
    }


async def main():
    parser = argparse.ArgumentParser(description="CanaryScope Docket Extraction Pipeline")
    parser.add_argument("--hearing-id", type=int, help="Process a specific hearing")
    parser.add_argument("--all-new", action="store_true", help="Process all new hearings")
    parser.add_argument("--reprocess-all", action="store_true", help="Reprocess all hearings")
    parser.add_argument("--no-notify", action="store_true", help="Disable notifications")

    args = parser.parse_args()
    notify = not args.no_notify

    with SessionLocal() as db:
        if args.hearing_id:
            result = await process_hearing(db, args.hearing_id, notify)
        elif args.all_new:
            result = await process_all_new_hearings(db, notify)
        elif args.reprocess_all:
            # Clear existing links and reprocess
            db.execute(text("DELETE FROM hearing_dockets"))
            db.commit()
            result = await process_all_new_hearings(db, notify)
        else:
            parser.print_help()
            return

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
