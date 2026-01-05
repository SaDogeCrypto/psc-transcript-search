#!/usr/bin/env python3
"""
PSC Transcript Post-Processor

Cleans up common Whisper transcription errors for regulatory terminology.
Run after transcription, before loading into database.

Usage:
    python psc_transcript_cleaner.py input.json output.json
    python psc_transcript_cleaner.py --directory ./data/transcripts/
"""

import json
import re
import argparse
from pathlib import Path
from typing import Dict, List, Tuple

# =============================================================================
# REPLACEMENT RULES
# =============================================================================

# Simple word/phrase replacements (case-insensitive matching, preserves case pattern)
WORD_REPLACEMENTS = {
    # Company names
    "george power": "Georgia Power",
    "georgia power company": "Georgia Power Company",
    "walt me mc": "Walton EMC",
    "walton me mc": "Walton EMC",
    "walton e m c": "Walton EMC",
    "waltonemc": "Walton EMC",
    "jackson emc": "Jackson EMC",
    "jackson e m c": "Jackson EMC",
    "douglas county emc": "Douglas County EMC",
    "central georgia emc": "Central Georgia EMC",
    "carroll emc": "Carroll EMC",
    "southern company": "Southern Company",
    "next era": "NextEra",
    "nextera": "NextEra",

    # Government/Legal entities
    "george springboard": "Georgia Supreme Court",
    "georgia springboard": "Georgia Supreme Court",
    "george spring port": "Georgia Supreme Court",
    "georgia spring port": "Georgia Supreme Court",
    "george spring board": "Georgia Supreme Court",
    "georgia spring board": "Georgia Supreme Court",
    "georgia court of appeals": "Georgia Court of Appeals",
    "george court of appeals": "Georgia Court of Appeals",
    "fulton county superior court": "Fulton County Superior Court",
    "public service commission": "Public Service Commission",
    "p s c": "PSC",

    # Legal terms
    "o c g a": "OCGA",
    "ocda": "OCGA",
    "o cga": "OCGA",
    "territorial act": "Territorial Act",
    "territory act": "Territorial Act",
    "territorial": "Territorial Act",  # context-dependent, may need refinement
    "grandfather clause": "grandfather clause",
    "grandfather falls": "grandfather clause",
    "grandfather's flaws": "grandfather clause",
    "summary judgment": "summary judgment",
    "summer judgment": "summary judgment",
    "some re-education": "summary adjudication",
    "summary of education": "summary adjudication",
    "summary adjudication": "summary adjudication",
    "evidentiary hearing": "evidentiary hearing",
    "evidentiary here": "evidentiary hearing",

    # Technical/utility terms
    "kilowatt": "kilowatt",
    "killer one": "kilowatt",
    "kilo watt": "kilowatt",
    "kilowatts": "kilowatts",
    "killer once": "kilowatts",
    "megawatt": "megawatt",
    "mega watt": "megawatt",
    "megahertz": "megawatts",  # common Whisper error in utility context
    "kva": "kVA",
    "k v a": "kVA",
    # Note: transform/transforms handled by regex below for word boundaries
    "voltage regulars": "voltage regulators",
    "involved to regulators": "voltage regulators",
    "conduit line": "conduit",

    # Procedural terms
    "pre filed": "pre-filed",
    "prefiled": "pre-filed",
    "pre found": "pre-filed",
    "refibrate": "reply brief",
    "rebuttal testimony": "rebuttal testimony",
    "library": "reply brief",  # context-dependent
    "briefing": "briefing",
    "motion for summary": "motion for summary",
    "motion summary": "motion for summary",
    "hearing officer": "Hearing Officer",
    "administrative session": "Administrative Session",

    # Common mishearings
    "hard as well": "Cartersville",
    "carter phil": "Cartersville",
    "carters ville": "Cartersville",
    "carter's ville": "Cartersville",
    "cartersville": "Cartersville",
    "card roll": "Cartersville",
    "carter's or": "Cartersville",
    "car as well": "Cartersville",
    "carsville": "Cartersville",
    "at four": "Acker",  # company name from transcript
    "act for": "Acker",
    "act or": "Acker",
    "at or": "Acker",
    "echo": "Acker",  # in this context
    "echor": "Acker",
    "act course": "Acker's",
    "at fours": "Acker's",
    "act fours": "Acker's",
    "at wars": "Acker's",
    "act wars": "Acker's",
    "hines": "Hines",  # developer name
    "finds": "Hines",  # common mishearing
}

# Regex patterns for more complex replacements
REGEX_REPLACEMENTS = [
    # Docket numbers - various formats
    (r"docu(?:ment)?\s*(?:number|no\.?)?\s*(\d+)\s*(?:thought|dot|/)?\s*(\d+)", r"Docket No. \1-\2"),
    (r"docket\s*(?:number|no\.?)?\s*#?\s*(\d+)", r"Docket No. \1"),
    (r"docket\s*#?\s*(\d+)\s*(?:and|&)\s*#?\s*(\d+)", r"Docket Nos. \1 and \2"),
    (r"docu\s+number\s+five\s+thought\s+973", "Docket No. 55973"),

    # OCGA citations
    (r"o\s*c\s*g\s*a\s*(?:section)?\s*(\d+)[- ](\d+)[- ](\d+)\s*(?:sub\s*)?(?:part\s*)?([a-z])?", r"OCGA §\1-\2-\3(\4)"),
    (r"section\s*(\d+)[- ](\d+)[- ](\d+)\s*(?:sub\s*)?(?:part\s*)?([a-z])?", r"§\1-\2-\3(\4)"),
    # Clean up empty parens from above
    (r"\(\)", ""),

    # KW/MW with numbers
    (r"(\d+)\s*(?:kilo\s*watts?|killer?\s*(?:one|once|watts?))", r"\1 kW"),
    (r"(\d+)\s*(?:mega\s*watts?|mega\s*hertz)", r"\1 MW"),
    (r"(\d+)\s*k\s*v\s*a", r"\1 kVA"),

    # Monetary amounts
    (r"\$?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:million|mil)", r"$\1 million"),
    (r"(\d+(?:\.\d+)?)\s*(?:million)\s*dollars?", r"$\1 million"),

    # Common phrase fixes
    (r"in\s+our\s+faith", "in our favor"),
    (r"in\s+substantial\s+(?:kind|time)", "in substantial kind"),
    (r"not\s+reconstruct(?:ed)?\s+(?:and|in)\s+substantial", "not reconstructed in substantial"),
    (r"destroyed\s+or\s+dismantled?\s+(?:and|in)\s+not", "destroyed or dismantled and not"),

    # Transform -> Transformer (with word boundary to avoid transformerer)
    (r"\btransform\b(?!er)", "transformer"),
    (r"\btransforms\b(?!er)", "transformers"),
]

# Speaker name patterns to standardize
SPEAKER_PATTERNS = [
    (r"(?:mr\.?|mister)\s+hewitt?s?(?:'?s)?(?:an)?", "Mr. Hewitson"),
    (r"(?:mr\.?|mister)\s+conn?[eo]r?l[ey]", "Mr. Connelly"),
    (r"(?:mr\.?|mister)\s+d[ae]?gl[ey]", "Mr. Dagle"),
    (r"(?:ms\.?|miss|mrs\.?)\s+beesman", "Ms. Beesman"),
    (r"(?:mr\.?|mister)\s+br[uo]tcher", "Mr. Brutcher"),
    (r"witness\s+br[uo]tcher", "Witness Brutcher"),
    (r"(?:mr\.?|mister)\s+benjamin", "Mr. Benjamin"),

    # Commissioner names (Georgia PSC)
    (r"commissioner\s+echols?", "Commissioner Echols"),
    (r"commissioner\s+shaw", "Commissioner Shaw"),
    (r"commissioner\s+johnson", "Commissioner Johnson"),
    (r"commissioner\s+mcdonald", "Commissioner McDonald"),
    (r"commissioner\s+pridemore", "Commissioner Pridemore"),
]

# =============================================================================
# PROCESSING FUNCTIONS
# =============================================================================

def apply_word_replacements(text: str, replacements: Dict[str, str]) -> str:
    """Apply simple word/phrase replacements."""
    result = text
    for pattern, replacement in replacements.items():
        # Case-insensitive replacement
        regex = re.compile(re.escape(pattern), re.IGNORECASE)
        result = regex.sub(replacement, result)
    return result

def apply_regex_replacements(text: str, patterns: List[Tuple[str, str]]) -> str:
    """Apply regex-based replacements."""
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result

def apply_speaker_patterns(text: str, patterns: List[Tuple[str, str]]) -> str:
    """Standardize speaker name references."""
    result = text
    for pattern, replacement in patterns:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result

def clean_transcript_text(text: str) -> str:
    """Apply all cleaning rules to transcript text."""
    # Order matters - apply in sequence
    result = text

    # 1. Apply regex patterns first (more specific)
    result = apply_regex_replacements(result, REGEX_REPLACEMENTS)

    # 2. Apply speaker patterns
    result = apply_speaker_patterns(result, SPEAKER_PATTERNS)

    # 3. Apply word replacements (more general)
    result = apply_word_replacements(result, WORD_REPLACEMENTS)

    # 4. Clean up extra whitespace
    result = re.sub(r'\s+', ' ', result).strip()

    return result

def process_transcript_file(input_path: Path, output_path: Path = None) -> Dict:
    """Process a single transcript JSON file."""
    with open(input_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Handle different JSON structures
    if isinstance(data, dict):
        if 'segments' in data:
            # Whisper output format with segments
            for segment in data['segments']:
                if 'text' in segment:
                    segment['text'] = clean_transcript_text(segment['text'])
                    segment['original_text'] = segment.get('original_text', segment['text'])
        if 'text' in data:
            # Full text field
            data['text'] = clean_transcript_text(data['text'])
    elif isinstance(data, list):
        # List of segments
        for segment in data:
            if isinstance(segment, dict) and 'text' in segment:
                segment['original_text'] = segment['text']
                segment['text'] = clean_transcript_text(segment['text'])

    # Save if output path provided
    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return data

def process_directory(directory: Path, suffix: str = '_cleaned') -> List[Path]:
    """Process all JSON files in a directory."""
    processed = []
    for json_file in directory.glob('*.json'):
        if suffix in json_file.stem:
            continue  # Skip already-processed files

        output_path = json_file.with_stem(f"{json_file.stem}{suffix}")
        process_transcript_file(json_file, output_path)
        processed.append(output_path)
        print(f"Processed: {json_file.name} -> {output_path.name}")

    return processed

# =============================================================================
# TESTING / DEMO
# =============================================================================

def demo():
    """Demonstrate the cleaner on sample text."""
    samples = [
        "Docu number five thought 973.",
        "george springboard said premises does not have to be known.",
        "The premises had a connected load of 900 killer one.",
        "o c g a section 46-3-8 sub part A.",
        "Mr. Hewitt's an aggressive on argument.",
        "walt me mc versus George power.",
        "carter phil versus joint power company.",
        "at four then converted premises to an actual manufacturing facility.",
        "act course expected use of the properties overnight.",
        "1.5 megahertz requiring a 1500 KVA transformer.",
        "They had to upgrade their switch and full additional secondary wire to each transform.",
    ]

    print("=" * 70)
    print("PSC Transcript Cleaner - Demo")
    print("=" * 70)

    for sample in samples:
        cleaned = clean_transcript_text(sample)
        print(f"\nOriginal:  {sample}")
        print(f"Cleaned:   {cleaned}")

    print("\n" + "=" * 70)

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Clean up PSC hearing transcripts from Whisper"
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Input JSON file or --demo for demonstration"
    )
    parser.add_argument(
        "output",
        nargs="?",
        help="Output JSON file (optional, defaults to input_cleaned.json)"
    )
    parser.add_argument(
        "--directory", "-d",
        help="Process all JSON files in directory"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demonstration on sample text"
    )

    args = parser.parse_args()

    if args.demo or args.input == "--demo":
        demo()
    elif args.directory:
        processed = process_directory(Path(args.directory))
        print(f"\nProcessed {len(processed)} files")
    elif args.input:
        input_path = Path(args.input)
        output_path = Path(args.output) if args.output else input_path.with_stem(f"{input_path.stem}_cleaned")
        process_transcript_file(input_path, output_path)
        print(f"Cleaned transcript saved to: {output_path}")
    else:
        parser.print_help()
