"""
Download audio from YouTube videos using yt-dlp.
Only downloads audio (not video) to save bandwidth and storage.
"""

import json
import subprocess
from pathlib import Path

DATA_DIR = Path("data")
AUDIO_DIR = DATA_DIR / "audio"


def download_audio(video_id: str, output_dir: Path) -> Path:
    """Download audio only from YouTube video."""
    output_path = output_dir / f"{video_id}.mp3"

    if output_path.exists():
        print(f"Already downloaded: {video_id}")
        return output_path

    cmd = [
        "yt-dlp",
        "-x",  # Extract audio
        "--audio-format", "mp3",
        "--audio-quality", "0",  # Best quality
        "-o", str(output_path),
        f"https://www.youtube.com/watch?v={video_id}"
    ]

    subprocess.run(cmd, check=True)
    return output_path


def main():
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    # Load video list
    video_list_path = DATA_DIR / "video_list.json"
    with open(video_list_path) as f:
        videos = json.load(f)

    print(f"Downloading audio for {len(videos)} videos...")

    for i, video in enumerate(videos):
        video_id = video["youtube_id"]
        title = video["title"][:50]
        print(f"[{i+1}/{len(videos)}] Downloading: {title}...")

        try:
            download_audio(video_id, AUDIO_DIR)
        except subprocess.CalledProcessError as e:
            print(f"  Error downloading {video_id}: {e}")
            continue

    print("Done!")


if __name__ == "__main__":
    main()
