"""
Fetch list of videos from Georgia PSC YouTube channel.
Filter for relevant hearings (Georgia Power, capacity, IRP, etc.)
Save metadata to JSON for processing.
"""

import subprocess
import json
from pathlib import Path

CHANNEL_URL = "https://www.youtube.com/@GeorgiaPublicServiceCommission/videos"
OUTPUT_DIR = Path("data")

# Keywords to filter for electric/Georgia Power content
INCLUDE_KEYWORDS = [
    "georgia power", "docket 56", "docket 44", "capacity",
    "irp", "integrated resource", "rate case", "energy committee"
]

EXCLUDE_KEYWORDS = [
    "telecom", "telecommunications", "natural gas only", "water"
]


def fetch_video_list():
    """Use yt-dlp to get video metadata from channel."""
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--print", "%(id)s|%(title)s|%(duration)s|%(upload_date)s|%(description)s",
        CHANNEL_URL
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    videos = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("|")
        if len(parts) >= 4:
            videos.append({
                "youtube_id": parts[0],
                "title": parts[1],
                "duration_seconds": int(parts[2]) if parts[2] and parts[2].isdigit() else 0,
                "upload_date": parts[3],
                "description": parts[4] if len(parts) > 4 else ""
            })

    return videos


def filter_relevant_videos(videos):
    """Filter for Georgia Power / electric related content."""
    relevant = []
    for video in videos:
        title_lower = video["title"].lower()
        desc_lower = video.get("description", "").lower()
        combined = title_lower + " " + desc_lower

        # Check exclusions first
        if any(kw in combined for kw in EXCLUDE_KEYWORDS):
            continue

        # Check inclusions
        if any(kw in combined for kw in INCLUDE_KEYWORDS):
            relevant.append(video)

    return relevant


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("Fetching video list from Georgia PSC channel...")
    all_videos = fetch_video_list()
    print(f"Found {len(all_videos)} total videos")

    relevant = filter_relevant_videos(all_videos)
    print(f"Found {len(relevant)} relevant videos after filtering")

    # Save to JSON
    output_path = OUTPUT_DIR / "video_list.json"
    with open(output_path, "w") as f:
        json.dump(relevant, f, indent=2)

    print(f"Saved to {output_path}")

    # Print summary
    total_hours = sum(v["duration_seconds"] for v in relevant) / 3600
    print(f"Total duration: {total_hours:.1f} hours")


if __name__ == "__main__":
    main()
