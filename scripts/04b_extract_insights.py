#!/usr/bin/env python3
"""
PSC Transcript Insight Extractor

Extracts structured intelligence from hearing transcripts using LLMs.
Two-tier approach:
  - Tier 1: Per-segment extraction (cheap, GPT-4o-mini)
  - Tier 2: Full-hearing analysis (comprehensive, GPT-4o)

Usage:
    python 04b_extract_insights.py                    # Process all hearings
    python 04b_extract_insights.py --hearing-id abc   # Process specific hearing
    python 04b_extract_insights.py --tier1-only       # Only segment extraction
    python 04b_extract_insights.py --tier2-only       # Only hearing analysis
    python 04b_extract_insights.py --estimate-cost    # Show cost estimate without running
"""

import json
import os
import asyncio
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from openai import AsyncOpenAI
import tiktoken

# =============================================================================
# CONFIGURATION
# =============================================================================

# Models
TIER1_MODEL = "gpt-4o-mini"  # Fast, cheap - $0.15/1M input, $0.60/1M output
TIER2_MODEL = "gpt-4o"       # Comprehensive - $2.50/1M input, $10/1M output

# Paths
DATA_DIR = Path("./data")
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
INSIGHTS_DIR = DATA_DIR / "insights"
SEGMENTS_DIR = DATA_DIR / "segments"

# Rate limiting
MAX_CONCURRENT_REQUESTS = 10
REQUESTS_PER_MINUTE = 500  # OpenAI tier limits

# =============================================================================
# SCHEMAS
# =============================================================================

@dataclass
class SegmentInsights:
    """Tier 1: Per-segment extraction"""
    segment_id: str
    speaker_name: Optional[str]
    speaker_role: Optional[str]  # attorney, witness, commissioner, hearing_officer, staff, intervenor
    speaker_affiliation: Optional[str]  # Georgia Power, PSC Staff, Sierra Club, etc.
    topics: List[str]
    entities: Dict[str, List[str]]  # {companies: [], docket_numbers: [], dollar_amounts: [], mw_figures: [], dates: []}
    segment_type: str  # testimony, cross_examination, ruling, procedural, colloquy, objection
    tone: str  # neutral, contentious, evasive, cooperative, emphatic
    key_claim: Optional[str]  # One-sentence summary if substantive
    is_notable: bool  # Flag for human review
    notable_reason: Optional[str]

@dataclass
class HearingInsights:
    """Tier 2: Full-hearing analysis"""
    hearing_id: str
    docket_numbers: List[str]
    hearing_date: str
    hearing_type: str  # evidentiary, oral_argument, public_comment, administrative
    duration_minutes: int

    # Participants
    parties: List[Dict[str, str]]  # [{name, role, attorney, position}]
    commissioners_present: List[str]
    hearing_officer: Optional[str]

    # Executive Summary
    executive_summary: str  # 2-3 paragraphs
    key_takeaways: List[str]  # 5-7 bullet points
    one_sentence_summary: str

    # Analysis
    central_dispute: str
    utility_position: str
    opposition_position: str
    staff_recommendation: Optional[str]

    # Commissioner Insights
    commissioner_concerns: List[Dict[str, str]]  # [{commissioner, concern, frequency}]
    commissioner_mood: str  # skeptical, supportive, neutral, mixed

    # Strategic Intelligence
    utility_vulnerabilities: List[str]  # Weaknesses exposed in cross
    utility_commitments: List[str]  # Statements that could be enforced
    disputed_facts: List[Dict[str, str]]  # [{fact, utility_position, opposition_position}]
    precedents_cited: List[Dict[str, str]]  # [{case, cited_by, for_proposition}]

    # Key Moments
    notable_exchanges: List[Dict[str, str]]  # [{timestamp, participants, description, significance}]
    potential_outcomes: List[Dict[str, str]]  # [{outcome, likelihood, reasoning}]

    # Metadata
    extracted_at: str
    model_used: str
    confidence_score: float  # 0-1, self-assessed

# =============================================================================
# PROMPTS
# =============================================================================

TIER1_SYSTEM_PROMPT = """You are an expert analyst specializing in public utility commission (PSC/PUC) regulatory proceedings. You extract structured intelligence from hearing transcripts.

Context: PSC hearings are quasi-judicial proceedings where utilities seek approval for rates, resource plans, and major investments. Participants include utility attorneys/witnesses, PSC Staff, Commissioners, and intervenors (consumer advocates, environmental groups, industrial customers).

Your task: Analyze the transcript segment and extract structured data. Be precise and conservative - only extract what's clearly present."""

TIER1_USER_PROMPT = """Analyze this PSC hearing transcript segment and extract structured insights.

TRANSCRIPT SEGMENT:
---
{segment_text}
---

CONTEXT (if available):
- Hearing: {hearing_title}
- Docket: {docket_numbers}
- Timestamp: {timestamp}
- Previous speaker: {previous_speaker}

Extract the following as JSON:

{{
  "speaker_name": "Full name if identifiable, null otherwise",
  "speaker_role": "One of: attorney, witness, commissioner, hearing_officer, staff, intervenor, unknown",
  "speaker_affiliation": "Organization they represent (Georgia Power, PSC Staff, Sierra Club, etc.) or null",
  "topics": ["List of 1-5 topics discussed, e.g., 'rate impact', 'load forecast', 'coal retirement'"],
  "entities": {{
    "companies": ["Company names mentioned"],
    "docket_numbers": ["Docket numbers in format XX-XXXXX"],
    "dollar_amounts": ["$X million, $X billion, etc."],
    "mw_figures": ["XXX MW capacity figures"],
    "dates": ["Specific dates or timeframes mentioned"]
  }},
  "segment_type": "One of: testimony, cross_examination, ruling, procedural, colloquy, objection, opening_statement, closing_argument",
  "tone": "One of: neutral, contentious, evasive, cooperative, emphatic, defensive",
  "key_claim": "One sentence summarizing the key substantive claim, or null if purely procedural",
  "is_notable": true/false - flag if this contains: admission against interest, commissioner concern, commitment, disputed fact, or significant ruling,
  "notable_reason": "Brief explanation if is_notable is true, null otherwise"
}}

Return ONLY valid JSON, no markdown formatting."""

TIER2_SYSTEM_PROMPT = """You are a senior regulatory affairs analyst preparing an intelligence briefing on a PSC hearing for executives at a competitive power company. Your analysis will inform bidding strategy, regulatory positioning, and market intelligence.

Your briefings are known for:
1. Cutting through procedural noise to surface strategic intelligence
2. Identifying commissioner concerns that predict decisions
3. Spotting utility vulnerabilities and commitments
4. Providing actionable insights, not just summaries

Context on PSC proceedings:
- Evidentiary hearings are formal, with sworn testimony and cross-examination
- Commissioner questions often telegraph their concerns and likely votes
- Staff recommendations are influential but not binding
- Utility commitments made on the record can be enforced in future proceedings
- Intervenors (Sierra Club, industrial customers, consumer advocates) often expose weaknesses

Write for a sophisticated audience that understands utility regulation."""

TIER2_USER_PROMPT = """Analyze this complete PSC hearing transcript and produce a comprehensive intelligence briefing.

HEARING METADATA:
- Title: {hearing_title}
- Docket(s): {docket_numbers}
- Date: {hearing_date}
- Duration: {duration_minutes} minutes
- Type: {hearing_type}

FULL TRANSCRIPT:
---
{full_transcript}
---

Produce a JSON intelligence briefing with the following structure:

{{
  "executive_summary": "2-3 paragraphs summarizing what happened, what it means, and what to watch for. Write for a busy executive.",

  "key_takeaways": [
    "5-7 bullet points of actionable intelligence",
    "Focus on: decisions made, commitments given, vulnerabilities exposed, timeline implications"
  ],

  "one_sentence_summary": "If you only remember one thing from this hearing, it should be...",

  "central_dispute": "What is the core disagreement this hearing addressed?",

  "utility_position": "Summary of what the utility is asking for and their key arguments",

  "opposition_position": "Summary of opposition arguments (Staff, intervenors)",

  "staff_recommendation": "PSC Staff position if stated, null if not discussed",

  "commissioner_concerns": [
    {{
      "commissioner": "Name",
      "concern": "What they seem worried about",
      "frequency": "How often they raised it (once, repeatedly, dominated discussion)"
    }}
  ],

  "commissioner_mood": "Overall commissioner sentiment: skeptical, supportive, neutral, mixed, hostile",

  "utility_vulnerabilities": [
    "Weaknesses exposed during cross-examination or commissioner questioning",
    "Inconsistencies with prior positions",
    "Data gaps or methodology issues"
  ],

  "utility_commitments": [
    "Specific commitments made on the record that could be enforced",
    "Include speaker name and what they committed to"
  ],

  "disputed_facts": [
    {{
      "fact": "What's being disputed",
      "utility_position": "Utility's claim",
      "opposition_position": "Opposition's claim"
    }}
  ],

  "precedents_cited": [
    {{
      "case": "Case name or docket",
      "cited_by": "Who cited it",
      "for_proposition": "What principle they cited it for"
    }}
  ],

  "notable_exchanges": [
    {{
      "timestamp": "Approximate time or segment reference",
      "participants": "Who was involved",
      "description": "What happened",
      "significance": "Why it matters"
    }}
  ],

  "potential_outcomes": [
    {{
      "outcome": "Possible decision",
      "likelihood": "high/medium/low",
      "reasoning": "Based on what was observed"
    }}
  ],

  "confidence_score": 0.0-1.0 (your confidence in this analysis given transcript quality)
}}

Return ONLY valid JSON, no markdown formatting."""

# =============================================================================
# LLM CLIENT
# =============================================================================

class InsightExtractor:
    def __init__(self, require_client: bool = True):
        api_key = os.getenv("OPENAI_API_KEY")
        if require_client and api_key:
            self.client = AsyncOpenAI(api_key=api_key)
        else:
            self.client = None
        self.encoding = tiktoken.encoding_for_model("gpt-4o")
        self.semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.encoding.encode(text))

    def estimate_cost(self, segments: List[Dict], full_transcript: str) -> Dict[str, float]:
        """Estimate API costs before running."""
        # Tier 1 costs
        tier1_input_tokens = sum(
            self.count_tokens(TIER1_SYSTEM_PROMPT) +
            self.count_tokens(s.get('text', '')) + 200  # prompt overhead
            for s in segments
        )
        tier1_output_tokens = len(segments) * 300  # ~300 tokens per response

        # Tier 2 costs
        tier2_input_tokens = (
            self.count_tokens(TIER2_SYSTEM_PROMPT) +
            self.count_tokens(full_transcript) + 500  # prompt overhead
        )
        tier2_output_tokens = 2000  # ~2000 tokens for full analysis

        # Pricing (per 1M tokens)
        tier1_cost = (tier1_input_tokens * 0.15 + tier1_output_tokens * 0.60) / 1_000_000
        tier2_cost = (tier2_input_tokens * 2.50 + tier2_output_tokens * 10.00) / 1_000_000

        return {
            "tier1": {
                "segments": len(segments),
                "input_tokens": tier1_input_tokens,
                "output_tokens": tier1_output_tokens,
                "estimated_cost": round(tier1_cost, 4)
            },
            "tier2": {
                "input_tokens": tier2_input_tokens,
                "output_tokens": tier2_output_tokens,
                "estimated_cost": round(tier2_cost, 4)
            },
            "total_estimated_cost": round(tier1_cost + tier2_cost, 4)
        }

    async def extract_segment_insights(
        self,
        segment: Dict,
        hearing_context: Dict
    ) -> SegmentInsights:
        """Tier 1: Extract insights from a single segment."""
        async with self.semaphore:
            prompt = TIER1_USER_PROMPT.format(
                segment_text=segment.get('text', ''),
                hearing_title=hearing_context.get('title', 'Unknown'),
                docket_numbers=hearing_context.get('docket_numbers', 'Unknown'),
                timestamp=segment.get('start_time', 'Unknown'),
                previous_speaker=hearing_context.get('previous_speaker', 'Unknown')
            )

            try:
                response = await self.client.chat.completions.create(
                    model=TIER1_MODEL,
                    messages=[
                        {"role": "system", "content": TIER1_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.1,
                    response_format={"type": "json_object"}
                )

                result = json.loads(response.choices[0].message.content)

                return SegmentInsights(
                    segment_id=segment.get('id', str(segment.get('segment_index', ''))),
                    speaker_name=result.get('speaker_name'),
                    speaker_role=result.get('speaker_role'),
                    speaker_affiliation=result.get('speaker_affiliation'),
                    topics=result.get('topics', []),
                    entities=result.get('entities', {}),
                    segment_type=result.get('segment_type', 'unknown'),
                    tone=result.get('tone', 'neutral'),
                    key_claim=result.get('key_claim'),
                    is_notable=result.get('is_notable', False),
                    notable_reason=result.get('notable_reason')
                )
            except Exception as e:
                print(f"Error processing segment {segment.get('id')}: {e}")
                return SegmentInsights(
                    segment_id=segment.get('id', 'error'),
                    speaker_name=None,
                    speaker_role='unknown',
                    speaker_affiliation=None,
                    topics=[],
                    entities={},
                    segment_type='unknown',
                    tone='neutral',
                    key_claim=None,
                    is_notable=False,
                    notable_reason=f"Error: {str(e)}"
                )

    async def extract_hearing_insights(
        self,
        hearing_metadata: Dict,
        full_transcript: str
    ) -> HearingInsights:
        """Tier 2: Extract comprehensive insights from full hearing."""

        # Truncate if too long (GPT-4o context is 128K but let's be conservative)
        max_tokens = 100_000
        if self.count_tokens(full_transcript) > max_tokens:
            # Truncate middle, keep beginning and end
            lines = full_transcript.split('\n')
            target_lines = int(len(lines) * 0.7)  # Keep ~70%
            keep_start = target_lines // 2
            keep_end = target_lines // 2
            truncated_lines = lines[:keep_start] + ["\n[... TRANSCRIPT TRUNCATED FOR LENGTH ...]\n"] + lines[-keep_end:]
            full_transcript = '\n'.join(truncated_lines)

        prompt = TIER2_USER_PROMPT.format(
            hearing_title=hearing_metadata.get('title', 'Unknown'),
            docket_numbers=hearing_metadata.get('docket_numbers', 'Unknown'),
            hearing_date=hearing_metadata.get('date', 'Unknown'),
            duration_minutes=hearing_metadata.get('duration_minutes', 0),
            hearing_type=hearing_metadata.get('hearing_type', 'evidentiary'),
            full_transcript=full_transcript
        )

        try:
            response = await self.client.chat.completions.create(
                model=TIER2_MODEL,
                messages=[
                    {"role": "system", "content": TIER2_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
                max_tokens=4000
            )

            result = json.loads(response.choices[0].message.content)

            return HearingInsights(
                hearing_id=hearing_metadata.get('id', 'unknown'),
                docket_numbers=hearing_metadata.get('docket_numbers', []),
                hearing_date=hearing_metadata.get('date', ''),
                hearing_type=hearing_metadata.get('hearing_type', 'evidentiary'),
                duration_minutes=hearing_metadata.get('duration_minutes', 0),
                parties=result.get('parties', []),
                commissioners_present=result.get('commissioners_present', []),
                hearing_officer=result.get('hearing_officer'),
                executive_summary=result.get('executive_summary', ''),
                key_takeaways=result.get('key_takeaways', []),
                one_sentence_summary=result.get('one_sentence_summary', ''),
                central_dispute=result.get('central_dispute', ''),
                utility_position=result.get('utility_position', ''),
                opposition_position=result.get('opposition_position', ''),
                staff_recommendation=result.get('staff_recommendation'),
                commissioner_concerns=result.get('commissioner_concerns', []),
                commissioner_mood=result.get('commissioner_mood', 'neutral'),
                utility_vulnerabilities=result.get('utility_vulnerabilities', []),
                utility_commitments=result.get('utility_commitments', []),
                disputed_facts=result.get('disputed_facts', []),
                precedents_cited=result.get('precedents_cited', []),
                notable_exchanges=result.get('notable_exchanges', []),
                potential_outcomes=result.get('potential_outcomes', []),
                extracted_at=datetime.now().isoformat(),
                model_used=TIER2_MODEL,
                confidence_score=result.get('confidence_score', 0.5)
            )
        except Exception as e:
            print(f"Error processing hearing {hearing_metadata.get('id')}: {e}")
            raise

# =============================================================================
# PIPELINE
# =============================================================================

async def process_hearing(
    hearing_id: str,
    extractor: InsightExtractor,
    tier1: bool = True,
    tier2: bool = True,
    estimate_only: bool = False
) -> Dict[str, Any]:
    """Process a single hearing through the insight extraction pipeline."""

    # Load transcript and segments
    transcript_path = TRANSCRIPTS_DIR / f"{hearing_id}.json"
    segments_path = SEGMENTS_DIR / f"{hearing_id}_segments.json"

    if not transcript_path.exists():
        # Try alternate naming
        transcript_files = list(TRANSCRIPTS_DIR.glob(f"*{hearing_id}*.json"))
        if transcript_files:
            transcript_path = transcript_files[0]
        else:
            raise FileNotFoundError(f"No transcript found for hearing {hearing_id}")

    with open(transcript_path, 'r') as f:
        transcript_data = json.load(f)

    # Extract segments and full text
    if isinstance(transcript_data, dict):
        segments = transcript_data.get('segments', [])
        full_text = transcript_data.get('text', '')
        if not full_text and segments:
            full_text = '\n'.join(s.get('text', '') for s in segments)
    elif isinstance(transcript_data, list):
        segments = transcript_data
        full_text = '\n'.join(s.get('text', '') for s in segments)
    else:
        raise ValueError(f"Unknown transcript format for {hearing_id}")

    # Build hearing metadata
    hearing_metadata = {
        'id': hearing_id,
        'title': transcript_data.get('title', hearing_id),
        'docket_numbers': transcript_data.get('docket_numbers', []),
        'date': transcript_data.get('date', ''),
        'duration_minutes': int(transcript_data.get('duration_seconds', 0) / 60),
        'hearing_type': transcript_data.get('hearing_type', 'evidentiary')
    }

    # Cost estimate
    cost_estimate = extractor.estimate_cost(segments, full_text)

    if estimate_only:
        return {
            'hearing_id': hearing_id,
            'segments_count': len(segments),
            'transcript_tokens': extractor.count_tokens(full_text),
            'cost_estimate': cost_estimate
        }

    print(f"\nProcessing hearing: {hearing_id}")
    print(f"  Segments: {len(segments)}")
    print(f"  Estimated cost: ${cost_estimate['total_estimated_cost']:.4f}")

    results = {
        'hearing_id': hearing_id,
        'processed_at': datetime.now().isoformat(),
        'cost_estimate': cost_estimate
    }

    # Tier 1: Segment extraction
    if tier1 and segments:
        print(f"  Running Tier 1 extraction on {len(segments)} segments...")

        hearing_context = {'title': hearing_metadata['title'], 'docket_numbers': hearing_metadata['docket_numbers']}

        tasks = []
        for i, segment in enumerate(segments):
            segment['id'] = segment.get('id', f"seg_{i}")
            hearing_context['previous_speaker'] = segments[i-1].get('speaker', 'Unknown') if i > 0 else 'None'
            tasks.append(extractor.extract_segment_insights(segment, hearing_context))

        segment_insights = await asyncio.gather(*tasks)
        results['segment_insights'] = [asdict(s) for s in segment_insights]

        # Summary stats
        notable_count = sum(1 for s in segment_insights if s.is_notable)
        print(f"  Tier 1 complete: {notable_count} notable segments flagged")

    # Tier 2: Full hearing analysis
    if tier2:
        print(f"  Running Tier 2 hearing analysis...")
        hearing_insights = await extractor.extract_hearing_insights(hearing_metadata, full_text)
        results['hearing_insights'] = asdict(hearing_insights)
        print(f"  Tier 2 complete: confidence {hearing_insights.confidence_score:.2f}")

    # Save results
    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = INSIGHTS_DIR / f"{hearing_id}_insights.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"  Saved to: {output_path}")

    return results


async def process_all_hearings(
    tier1: bool = True,
    tier2: bool = True,
    estimate_only: bool = False
) -> List[Dict]:
    """Process all available hearings."""

    extractor = InsightExtractor(require_client=not estimate_only)

    # Find all transcripts
    transcript_files = list(TRANSCRIPTS_DIR.glob("*.json"))

    if not transcript_files:
        print(f"No transcripts found in {TRANSCRIPTS_DIR}")
        return []

    print(f"Found {len(transcript_files)} transcripts")

    results = []
    total_cost = 0

    for transcript_file in transcript_files:
        hearing_id = transcript_file.stem.replace('_cleaned', '')

        try:
            result = await process_hearing(
                hearing_id,
                extractor,
                tier1=tier1,
                tier2=tier2,
                estimate_only=estimate_only
            )
            results.append(result)

            if 'cost_estimate' in result:
                total_cost += result['cost_estimate']['total_estimated_cost']

        except Exception as e:
            print(f"Error processing {hearing_id}: {e}")
            continue

    print(f"\n{'='*50}")
    if estimate_only:
        print(f"TOTAL ESTIMATED COST: ${total_cost:.4f}")
    else:
        print(f"Processed {len(results)} hearings")
        print(f"Total estimated API cost: ${total_cost:.4f}")

    return results


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Extract insights from PSC hearing transcripts")
    parser.add_argument("--hearing-id", help="Process specific hearing by ID")
    parser.add_argument("--tier1-only", action="store_true", help="Only run Tier 1 segment extraction")
    parser.add_argument("--tier2-only", action="store_true", help="Only run Tier 2 hearing analysis")
    parser.add_argument("--estimate-cost", action="store_true", help="Estimate cost without processing")
    parser.add_argument("--data-dir", default="./data", help="Data directory path")

    args = parser.parse_args()

    # Update paths if custom data dir
    global DATA_DIR, TRANSCRIPTS_DIR, INSIGHTS_DIR, SEGMENTS_DIR
    DATA_DIR = Path(args.data_dir)
    TRANSCRIPTS_DIR = DATA_DIR / "transcripts"
    INSIGHTS_DIR = DATA_DIR / "insights"
    SEGMENTS_DIR = DATA_DIR / "segments"

    # Determine what to run
    tier1 = not args.tier2_only
    tier2 = not args.tier1_only

    # Check for API key
    if not os.getenv("OPENAI_API_KEY") and not args.estimate_cost:
        print("Error: OPENAI_API_KEY environment variable not set")
        return

    if args.hearing_id:
        result = asyncio.run(process_hearing(
            args.hearing_id,
            InsightExtractor(require_client=not args.estimate_cost),
            tier1=tier1,
            tier2=tier2,
            estimate_only=args.estimate_cost
        ))
        if args.estimate_cost and result:
            print(f"\nHearing: {result['hearing_id']}")
            print(f"Segments: {result['segments_count']}")
            print(f"Transcript tokens: {result['transcript_tokens']}")
            cost = result['cost_estimate']
            print(f"\nTier 1 (segment extraction):")
            print(f"  Input tokens: {cost['tier1']['input_tokens']:,}")
            print(f"  Output tokens: {cost['tier1']['output_tokens']:,}")
            print(f"  Cost: ${cost['tier1']['estimated_cost']:.4f}")
            print(f"\nTier 2 (hearing analysis):")
            print(f"  Input tokens: {cost['tier2']['input_tokens']:,}")
            print(f"  Output tokens: {cost['tier2']['output_tokens']:,}")
            print(f"  Cost: ${cost['tier2']['estimated_cost']:.4f}")
            print(f"\nTOTAL ESTIMATED COST: ${cost['total_estimated_cost']:.4f}")
    else:
        asyncio.run(process_all_hearings(
            tier1=tier1,
            tier2=tier2,
            estimate_only=args.estimate_cost
        ))


if __name__ == "__main__":
    main()
