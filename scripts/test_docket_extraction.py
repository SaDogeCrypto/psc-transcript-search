"""
Docket Extraction Test Script

Run this against your existing transcripts to see what identifiers exist
and how consistently they're formatted.
"""

import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI()

EXTRACTION_PROMPT = """Analyze this transcript excerpt from a Public Service Commission hearing and extract all official proceeding identifiers.

Look for:
- Docket numbers (e.g., "Docket 44160", "Docket No. 2024-0034")
- Case numbers (e.g., "Case 24-001")
- Proceeding numbers (e.g., "A.24-01-001", "ER24-1234")
- Application numbers
- Any other official reference ID used to track this matter

For each identifier found, extract:
1. raw_text: The exact text as it appears
2. normalized_id: Your best attempt at a clean ID
3. type: What kind of proceeding (rate case, IRP, complaint, rulemaking, etc.)
4. company: Company involved if mentioned
5. description: Brief description if context available

Also note:
- confidence: high/medium/low
- If NO identifiers found, say so explicitly

Return JSON format:
{{
  "identifiers": [
    {{
      "raw_text": "Docket Number 44160",
      "normalized_id": "44160",
      "type": "rate case",
      "company": "Georgia Power",
      "description": "Base rate increase request",
      "confidence": "high"
    }}
  ],
  "no_identifiers_found": false,
  "notes": "Any relevant observations about format or ambiguity"
}}

TRANSCRIPT:
{transcript}
"""

def extract_dockets(transcript_text: str, state: str) -> dict:
    """Extract docket identifiers from a transcript."""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=1000,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": EXTRACTION_PROMPT.format(transcript=transcript_text[:15000])  # Limit context
            }
        ]
    )

    # Parse response
    try:
        result = json.loads(response.choices[0].message.content)
        result["state"] = state
        return result
    except json.JSONDecodeError:
        return {
            "state": state,
            "error": "Failed to parse response",
            "raw_response": response.choices[0].message.content
        }


def test_on_existing_transcripts():
    """
    Load transcripts from SQLite database (psc_transcripts.db).
    Reconstructs full transcript from segments.
    """
    import sqlite3

    # Path to actual database with transcripts
    db_path = "/home/ronan/psc-transcript-search/data/psc_transcripts.db"

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all hearings
    cursor.execute("SELECT id, title FROM hearings")
    hearings = cursor.fetchall()
    print(f"Found {len(hearings)} hearings to process\n")

    results = []
    for hearing_id, title in hearings:
        # Infer state from title
        if "GA PSC" in title or "Georgia" in title:
            state = "GA"
        elif "CA CPUC" in title or "California" in title:
            state = "CA"
        elif "TX PUCT" in title or "Texas" in title:
            state = "TX"
        else:
            state = "UNKNOWN"

        # Reconstruct full transcript from segments
        cursor.execute("""
            SELECT text FROM segments
            WHERE hearing_id = ?
            ORDER BY segment_index
        """, (hearing_id,))
        segments = cursor.fetchall()
        full_transcript = " ".join([s[0] for s in segments if s[0]])

        if not full_transcript:
            print(f"Skipping {title[:50]}... (no transcript)")
            continue

        print(f"Processing: {state} - {title[:60]}...")
        print(f"  Transcript length: {len(full_transcript)} chars")

        result = extract_dockets(full_transcript, state)
        result["hearing_title"] = title
        result["hearing_id"] = hearing_id
        results.append(result)

        # Print summary
        if result.get("identifiers"):
            for ident in result["identifiers"]:
                print(f"  Found: {ident['raw_text']} -> {ident['normalized_id']} ({ident.get('type', 'unknown')})")
        elif result.get("no_identifiers_found"):
            print("  No identifiers found")
        else:
            print("  No identifiers found")
        print()

    conn.close()

    # Save full results
    output_path = "/home/ronan/psc-transcript-search/docket_extraction_results.json"
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Results saved to {output_path}")
    print(f"Processed {len(results)} hearings")

    # Summary by state
    by_state = {}
    for r in results:
        st = r.get("state", "UNKNOWN")
        if st not in by_state:
            by_state[st] = {"count": 0, "identifiers": 0}
        by_state[st]["count"] += 1
        by_state[st]["identifiers"] += len(r.get("identifiers", []))

    print("\nSummary by state:")
    for st, data in by_state.items():
        print(f"  {st}: {data['count']} hearings, {data['identifiers']} identifiers found")

    return results


def test_with_sample():
    """
    Test with a hardcoded sample if you don't want to hit the DB yet.
    """
    sample_transcript = """
    Good morning. This hearing is now in session. We are here today to consider
    Docket Number 44160, Georgia Power Company's request for a base rate increase.
    This is a continuation of our proceedings from December 20th.

    The company is seeking approval for a 12.5 percent increase in base rates,
    citing infrastructure investments and increased load from data center development.

    We will also briefly touch on Docket 44089, the integrated resource plan filing,
    as it relates to the capacity needs underlying this rate request.

    Commissioner Smith, would you like to begin?
    """

    result = extract_dockets(sample_transcript, "GA")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    # Run on all real transcripts
    print("=== Extracting dockets from all transcripts ===\n")
    test_on_existing_transcripts()
