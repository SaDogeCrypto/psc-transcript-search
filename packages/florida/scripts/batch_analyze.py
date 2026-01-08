#!/usr/bin/env python3
"""
Batch analyze Florida hearings using GPT-4o-mini.

Analyzes all hearings that don't have an analysis yet.
Saves summaries, commissioner sentiment, outcomes, etc.
"""

import os
import sys
import json
import time
import logging
from datetime import datetime

# Add package to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database
DATABASE_URL = os.getenv('FL_DATABASE_URL', 'postgresql://csadmin:6IyN%2A%40%2AbJ%23SmS2dCCYGJiL7Z@canaryscope-florida.postgres.database.azure.com/florida?sslmode=require')

# OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
MODEL = "gpt-4o-mini"

# Cost tracking
INPUT_COST_PER_1M = 0.15
OUTPUT_COST_PER_1M = 0.60

SYSTEM_PROMPT = """You are a senior regulatory affairs analyst specializing in public utility commission (PSC/PUC) proceedings. Your analysis will inform executives about regulatory developments.

Your briefings are known for:
1. Cutting through procedural noise to surface strategic intelligence
2. Identifying commissioner concerns that predict decisions
3. Spotting utility vulnerabilities and commitments
4. Providing actionable insights, not just summaries

Context on PSC proceedings:
- Evidentiary hearings are formal, with sworn testimony and cross-examination
- Commissioner questions often telegraph their concerns and likely votes
- Staff recommendations are influential but not binding
- Utility commitments made on the record can be enforced in future proceedings"""

USER_PROMPT = """Analyze this Florida PSC hearing transcript and produce a comprehensive intelligence briefing.

HEARING METADATA:
- Title: {title}
- Date: {hearing_date}
- Docket: {docket_number}

TRANSCRIPT:
---
{transcript_text}
---

Produce a JSON analysis with this structure:

{{
  "summary": "2-3 paragraph executive summary focusing on what matters to investors/stakeholders",
  "one_sentence_summary": "Single sentence capturing the key takeaway",
  "hearing_type": "rate case, fuel adjustment, certificate, complaint, rulemaking, or other",
  "utility_name": "Primary utility involved",
  "sector": "electric, gas, water, telecom, or multi",

  "participants": [
    {{"name": "Name", "role": "commissioner/witness/attorney/intervenor", "affiliation": "Organization"}}
  ],

  "issues": [
    {{"issue": "Key issue", "description": "Brief description", "stance_by_party": {{"utility": "position", "staff": "position", "opc": "position"}}}}
  ],

  "commitments": [
    {{"commitment": "What was committed", "by_whom": "Who made it", "context": "Why it matters", "binding": true/false}}
  ],

  "commissioner_concerns": [
    {{"commissioner": "Name", "concern": "What they're worried about", "severity": "high/medium/low"}}
  ],

  "commissioner_mood": "supportive, skeptical, hostile, neutral, or mixed",

  "likely_outcome": "Predicted outcome with reasoning",
  "outcome_confidence": 0.0-1.0,

  "risk_factors": [
    {{"factor": "Risk description", "likelihood": "high/medium/low", "impact": "high/medium/low"}}
  ],

  "quotes": [
    {{"speaker": "Name", "quote": "Notable quote (verbatim)", "timestamp": "if available", "significance": "Why it matters"}}
  ]
}}

Return ONLY valid JSON."""


def get_transcript_text(db, hearing_id: int, max_chars: int = 100000) -> str:
    """Get full transcript text from segments."""
    result = db.execute(text("""
        SELECT text FROM fl_transcript_segments
        WHERE hearing_id = :hearing_id
        ORDER BY segment_index
    """), {"hearing_id": hearing_id})

    segments = [row[0] for row in result.fetchall()]
    full_text = "\n".join(segments)

    if len(full_text) > max_chars:
        # Keep beginning and end
        half = max_chars // 2
        full_text = full_text[:half] + "\n\n[... TRANSCRIPT TRUNCATED ...]\n\n" + full_text[-half:]

    return full_text


def analyze_hearing(client: OpenAI, hearing: dict, transcript_text: str) -> dict:
    """Run GPT analysis on hearing transcript."""

    # Try to extract docket from title (common format: "... for Docket No. 20250123-XX")
    import re
    docket_match = re.search(r'(?:Docket\s*(?:No\.?\s*)?)?(\d{8}-[A-Z]{2})', hearing['title'])
    docket_number = docket_match.group(1) if docket_match else 'Unknown'

    prompt = USER_PROMPT.format(
        title=hearing['title'],
        hearing_date=hearing['hearing_date'].isoformat() if hearing['hearing_date'] else 'Unknown',
        docket_number=docket_number,
        transcript_text=transcript_text
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
                max_tokens=4000
            )

            content = response.choices[0].message.content
            data = json.loads(content)

            # Calculate cost
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            cost = (input_tokens * INPUT_COST_PER_1M / 1_000_000) + (output_tokens * OUTPUT_COST_PER_1M / 1_000_000)

            return {
                "success": True,
                "data": data,
                "cost_usd": cost,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens
            }

        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                wait = 60 * (2 ** attempt)
                logger.warning(f"Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue
            raise

    return {"success": False, "error": "Max retries exceeded"}


def save_analysis(db, hearing_id: int, result: dict):
    """Save analysis to fl_analyses table."""
    data = result['data']

    db.execute(text("""
        INSERT INTO fl_analyses (
            hearing_id, summary, one_sentence_summary, hearing_type, utility_name, sector,
            participants_json, issues_json, commitments_json, commissioner_concerns_json,
            commissioner_mood, likely_outcome, outcome_confidence, risk_factors_json, quotes_json,
            model, cost_usd, confidence_score, created_at
        ) VALUES (
            :hearing_id, :summary, :one_sentence_summary, :hearing_type, :utility_name, :sector,
            :participants, :issues, :commitments, :commissioner_concerns,
            :commissioner_mood, :likely_outcome, :outcome_confidence, :risk_factors, :quotes,
            :model, :cost_usd, :confidence_score, :created_at
        )
        ON CONFLICT (hearing_id) DO UPDATE SET
            summary = EXCLUDED.summary,
            one_sentence_summary = EXCLUDED.one_sentence_summary,
            hearing_type = EXCLUDED.hearing_type,
            utility_name = EXCLUDED.utility_name,
            sector = EXCLUDED.sector,
            participants_json = EXCLUDED.participants_json,
            issues_json = EXCLUDED.issues_json,
            commitments_json = EXCLUDED.commitments_json,
            commissioner_concerns_json = EXCLUDED.commissioner_concerns_json,
            commissioner_mood = EXCLUDED.commissioner_mood,
            likely_outcome = EXCLUDED.likely_outcome,
            outcome_confidence = EXCLUDED.outcome_confidence,
            risk_factors_json = EXCLUDED.risk_factors_json,
            quotes_json = EXCLUDED.quotes_json,
            model = EXCLUDED.model,
            cost_usd = EXCLUDED.cost_usd,
            confidence_score = EXCLUDED.confidence_score,
            created_at = EXCLUDED.created_at
    """), {
        "hearing_id": hearing_id,
        "summary": data.get("summary"),
        "one_sentence_summary": data.get("one_sentence_summary"),
        "hearing_type": data.get("hearing_type"),
        "utility_name": data.get("utility_name"),
        "sector": data.get("sector"),
        "participants": json.dumps(data.get("participants", [])),
        "issues": json.dumps(data.get("issues", [])),
        "commitments": json.dumps(data.get("commitments", [])),
        "commissioner_concerns": json.dumps(data.get("commissioner_concerns", [])),
        "commissioner_mood": data.get("commissioner_mood"),
        "likely_outcome": data.get("likely_outcome"),
        "outcome_confidence": data.get("outcome_confidence"),
        "risk_factors": json.dumps(data.get("risk_factors", [])),
        "quotes": json.dumps(data.get("quotes", [])),
        "model": MODEL,
        "cost_usd": result.get("cost_usd", 0),
        "confidence_score": data.get("outcome_confidence"),
        "created_at": datetime.utcnow()
    })
    db.commit()


def main(limit: int = 10):
    """Analyze unanalyzed hearings."""

    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set")
        sys.exit(1)

    engine = create_engine(DATABASE_URL)
    Session = sessionmaker(bind=engine)
    db = Session()

    client = OpenAI(api_key=OPENAI_API_KEY)

    # Get hearings with transcripts but without analysis
    result = db.execute(text("""
        SELECT h.id, h.title, h.hearing_date,
               COUNT(s.id) as segment_count
        FROM fl_hearings h
        JOIN fl_transcript_segments s ON s.hearing_id = h.id
        LEFT JOIN fl_analyses a ON a.hearing_id = h.id
        WHERE a.id IS NULL
        GROUP BY h.id, h.title, h.hearing_date
        HAVING COUNT(s.id) > 10
        ORDER BY COUNT(s.id) DESC
        LIMIT :limit
    """), {"limit": limit})

    hearings = [dict(row._mapping) for row in result.fetchall()]

    if not hearings:
        logger.info("All hearings have been analyzed!")
        return

    logger.info(f"Found {len(hearings)} hearings to analyze")

    total_cost = 0
    for i, hearing in enumerate(hearings, 1):
        logger.info(f"[{i}/{len(hearings)}] Analyzing: {hearing['title'][:60]}...")

        if hearing['segment_count'] == 0:
            logger.warning(f"  Skipping - no transcript segments")
            continue

        transcript = get_transcript_text(db, hearing['id'])
        if len(transcript) < 500:
            logger.warning(f"  Skipping - transcript too short ({len(transcript)} chars)")
            continue

        result = analyze_hearing(client, hearing, transcript)

        if result['success']:
            save_analysis(db, hearing['id'], result)
            total_cost += result['cost_usd']
            logger.info(f"  Done: ${result['cost_usd']:.4f} ({result['input_tokens']} in, {result['output_tokens']} out)")
            logger.info(f"  Mood: {result['data'].get('commissioner_mood')}, Outcome: {result['data'].get('likely_outcome', '')[:60]}...")
        else:
            logger.error(f"  Failed: {result.get('error')}")

        # Rate limit protection
        time.sleep(2)

    logger.info(f"\nTotal cost: ${total_cost:.4f}")
    db.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10, help="Max hearings to analyze")
    args = parser.parse_args()
    main(args.limit)
