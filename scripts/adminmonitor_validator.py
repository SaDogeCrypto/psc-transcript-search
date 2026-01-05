#!/usr/bin/env python3
"""
AdminMonitor Video Validation & Download Script
------------------------------------------------
Tests accessibility of California CPUC and Texas PUCT hearings
from AdminMonitor's archive.

FINDINGS FROM RESEARCH:
- AdminMonitor uses HLS streaming (m3u8 playlists)
- Videos hosted on CloudFront CDN (AWS)
- URLs exposed directly in page HTML
- NO DRM protection detected
- Archive goes back to 2014 for CPUC

Run this script locally (not in cloud containers with proxy restrictions).

Requirements:
    pip install requests beautifulsoup4 m3u8

Usage:
    python adminmonitor_validator.py
    python adminmonitor_validator.py --download
"""

import requests
import re
import sys
import json
from datetime import datetime
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

# Headers to avoid 403
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Connection": "keep-alive",
}

# Test URLs
TEST_PAGES = {
    "CPUC Hearing 2025-01-23": "https://www.adminmonitor.com/ca/cpuc/hearing/20250123/",
    "CPUC Hearing 2024-10-22": "https://www.adminmonitor.com/ca/cpuc/hearing/20241022/",
    "CPUC Hearing 2023-11-20": "https://www.adminmonitor.com/ca/cpuc/hearing/20231120/",
    "TX PUCT Open Meeting": "https://www.adminmonitor.com/tx/puct/open_meeting/",
}

# Archive listing pages
ARCHIVE_PAGES = {
    "CPUC Hearings": "https://www.adminmonitor.com/ca/cpuc/hearing/",
    "CPUC Voting Meetings": "https://www.adminmonitor.com/ca/cpuc/voting_meeting/",
    "CPUC Workshops": "https://www.adminmonitor.com/ca/cpuc/workshop/",
    "TX PUCT Open Meetings": "https://www.adminmonitor.com/tx/puct/open_meeting/",
    "TX PUCT Hearings": "https://www.adminmonitor.com/tx/puct/hearing_on_the_merits/",
}


def extract_video_urls(html_content):
    """Extract m3u8 video URLs from HTML"""
    patterns = [
        # CloudFront HLS
        r'https://[a-z0-9]+\.cloudfront\.net/videos/[^\s"\'<>]+\.m3u8',
        # Brightcove (backup)
        r'https://[a-z0-9]+\.brightcove[^\s"\'<>]+',
        # Generic m3u8
        r'https://[^\s"\'<>]+\.m3u8',
    ]

    urls = []
    for pattern in patterns:
        matches = re.findall(pattern, html_content)
        urls.extend(matches)

    return list(set(urls))


def extract_meeting_links(html_content, base_url):
    """Extract individual meeting page links from archive page"""
    if not BeautifulSoup:
        # Fallback regex if bs4 not installed
        pattern = r'href="(/[a-z]{2}/[a-z]+/[a-z_]+/\d{8,}/)"'
        matches = re.findall(pattern, html_content)
        return [f"https://www.adminmonitor.com{m}" for m in matches]

    soup = BeautifulSoup(html_content, 'html.parser')
    links = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        if re.match(r'/[a-z]{2}/[a-z]+/[a-z_]+/\d{8,}/', href):
            if href.startswith('/'):
                links.append(f"https://www.adminmonitor.com{href}")
            else:
                links.append(href)
    return list(set(links))


def test_url_accessibility(url, timeout=10):
    """Test if URL is accessible"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout, stream=True)
        return {
            "accessible": resp.status_code == 200,
            "status_code": resp.status_code,
            "content_type": resp.headers.get('content-type', 'unknown'),
            "content_length": resp.headers.get('content-length', 'unknown'),
        }
    except requests.RequestException as e:
        return {
            "accessible": False,
            "error": str(e)
        }


def test_m3u8_playlist(url, timeout=10):
    """Test m3u8 playlist and extract segment info"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code != 200:
            return {"accessible": False, "status_code": resp.status_code}

        content = resp.text
        lines = content.strip().split('\n')

        # Parse m3u8
        info = {
            "accessible": True,
            "is_master": "#EXT-X-STREAM-INF" in content,
            "line_count": len(lines),
            "preview": content[:500] if len(content) > 500 else content,
        }

        # Count segments or variants
        if info["is_master"]:
            info["variants"] = len(re.findall(r'#EXT-X-STREAM-INF', content))
        else:
            info["segments"] = len(re.findall(r'\.ts', content))

        return info

    except Exception as e:
        return {"accessible": False, "error": str(e)}


def run_validation():
    """Run full validation suite"""
    print("=" * 70)
    print("AdminMonitor Video Validation")
    print(f"Run time: {datetime.now().isoformat()}")
    print("=" * 70)

    results = {
        "timestamp": datetime.now().isoformat(),
        "pages_tested": [],
        "videos_found": [],
        "summary": {}
    }

    # Test individual hearing pages
    print("\n[1] Testing Individual Hearing Pages")
    print("-" * 50)

    for name, url in TEST_PAGES.items():
        print(f"\n  Testing: {name}")
        print(f"  URL: {url}")

        page_result = test_url_accessibility(url)

        if page_result.get("accessible"):
            print(f"  ✅ Page accessible")

            # Fetch full content and extract video URLs
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                video_urls = extract_video_urls(resp.text)

                if video_urls:
                    print(f"  📹 Found {len(video_urls)} video URL(s):")
                    for vurl in video_urls:
                        print(f"     {vurl[:80]}...")

                        # Test video accessibility
                        vtest = test_m3u8_playlist(vurl)
                        if vtest.get("accessible"):
                            print(f"     ✅ Video accessible! ", end="")
                            if vtest.get("is_master"):
                                print(f"(Master playlist, {vtest.get('variants', '?')} variants)")
                            else:
                                print(f"({vtest.get('segments', '?')} segments)")
                            results["videos_found"].append({
                                "page": name,
                                "url": vurl,
                                "info": vtest
                            })
                        else:
                            print(f"     ❌ Video not accessible: {vtest.get('error', vtest.get('status_code'))}")
                else:
                    print(f"  ⚠️  No video URLs found in page")
            except Exception as e:
                print(f"  ❌ Error fetching page: {e}")
        else:
            print(f"  ❌ Page not accessible: {page_result.get('error', page_result.get('status_code'))}")

        results["pages_tested"].append({
            "name": name,
            "url": url,
            "result": page_result
        })

    # Test archive pages to count available content
    print("\n\n[2] Counting Archive Content")
    print("-" * 50)

    for name, url in ARCHIVE_PAGES.items():
        print(f"\n  Archive: {name}")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                meeting_links = extract_meeting_links(resp.text, url)
                print(f"  📁 Found {len(meeting_links)} archived meetings")
                results["summary"][name] = len(meeting_links)
            else:
                print(f"  ❌ Status {resp.status_code}")
        except Exception as e:
            print(f"  ❌ Error: {e}")

    # Summary
    print("\n\n[3] Summary")
    print("-" * 50)

    total_videos = len(results["videos_found"])
    print(f"\n  Videos found and accessible: {total_videos}")

    if total_videos > 0:
        print("\n  ✅ AdminMonitor videos ARE downloadable!")
        print("\n  Download methods:")
        print("  1. ffmpeg (recommended):")
        print("     ffmpeg -i <m3u8_url> -c copy output.mp4")
        print("\n  2. yt-dlp:")
        print("     yt-dlp <m3u8_url> -o output.mp4")
        print("\n  3. Python + requests + m3u8 library")
    else:
        print("\n  ⚠️  No videos accessible from this environment")
        print("  This may be due to network restrictions.")
        print("  Try running from a different network.")

    # Archive totals
    total_archived = sum(results["summary"].values())
    print(f"\n  Total archived meetings indexed: {total_archived}")
    for name, count in results["summary"].items():
        print(f"    - {name}: {count}")

    # Save results
    output_file = Path("adminmonitor_validation_results.json")
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n  Results saved to: {output_file}")

    return results


def download_sample(url, output_path="sample_hearing.mp4"):
    """Download a sample video using ffmpeg"""
    import subprocess

    print(f"\nDownloading: {url}")
    print(f"Output: {output_path}")

    cmd = [
        "ffmpeg",
        "-i", url,
        "-c", "copy",
        "-y",  # Overwrite
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"✅ Download complete: {output_path}")
            return True
        else:
            print(f"❌ Download failed: {result.stderr}")
            return False
    except subprocess.TimeoutExpired:
        print("❌ Download timed out")
        return False
    except FileNotFoundError:
        print("❌ ffmpeg not found. Install with: sudo apt install ffmpeg")
        return False


if __name__ == "__main__":
    if "--download" in sys.argv:
        # Run validation and download first accessible video
        results = run_validation()
        if results["videos_found"]:
            first_video = results["videos_found"][0]
            print("\n" + "=" * 70)
            print("Downloading sample video...")
            download_sample(first_video["url"])
    else:
        run_validation()
