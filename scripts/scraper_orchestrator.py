#!/usr/bin/env python3
"""
Master Scraper Orchestrator

Runs all scraper types with progress tracking and error handling.
Can be controlled via API endpoints for start/stop operations.

Usage:
    python scripts/scraper_orchestrator.py                    # Run all scrapers
    python scripts/scraper_orchestrator.py --type youtube     # Run specific type
    python scripts/scraper_orchestrator.py --state CA         # Filter by state
    python scripts/scraper_orchestrator.py --dry-run          # Preview mode
"""

import sys
import os
import json
import argparse
import logging
import threading
import signal
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models.database import Source, Hearing, State

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ScraperStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class ScraperProgress:
    """Track scraper progress and results."""
    status: ScraperStatus = ScraperStatus.IDLE
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # Current task
    current_scraper_type: Optional[str] = None
    current_source_name: Optional[str] = None
    current_source_index: int = 0
    total_sources: int = 0

    # Overall stats
    sources_completed: int = 0
    items_found: int = 0
    new_hearings: int = 0
    existing_hearings: int = 0

    # Errors
    errors: list = field(default_factory=list)

    # Per-scraper breakdown
    scraper_results: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "current_scraper_type": self.current_scraper_type,
            "current_source_name": self.current_source_name,
            "current_source_index": self.current_source_index,
            "total_sources": self.total_sources,
            "sources_completed": self.sources_completed,
            "items_found": self.items_found,
            "new_hearings": self.new_hearings,
            "existing_hearings": self.existing_hearings,
            "errors": self.errors[-20:],  # Last 20 errors
            "error_count": len(self.errors),
            "scraper_results": self.scraper_results,
        }

    def add_error(self, source_name: str, error: str):
        """Add an error with timestamp."""
        self.errors.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": source_name,
            "error": error[:500]
        })


class ScraperOrchestrator:
    """
    Master orchestrator that runs all scraper types.
    Thread-safe with stop functionality.
    """

    def __init__(self):
        self.progress = ScraperProgress()
        self._stop_requested = threading.Event()
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return self.progress.status == ScraperStatus.RUNNING

    def request_stop(self):
        """Request the scraper to stop after current source."""
        if self.is_running:
            self._stop_requested.set()
            self.progress.status = ScraperStatus.STOPPING
            logger.info("Stop requested - will stop after current source")

    def get_progress(self) -> dict:
        """Get current progress as dict."""
        with self._lock:
            return self.progress.to_dict()

    def run_async(
        self,
        scraper_types: Optional[list[str]] = None,
        state_code: Optional[str] = None,
        dry_run: bool = False
    ):
        """Run scrapers in a background thread."""
        if self.is_running:
            raise RuntimeError("Scraper is already running")

        self._thread = threading.Thread(
            target=self._run,
            args=(scraper_types, state_code, dry_run),
            daemon=True
        )
        self._thread.start()

    def run(
        self,
        scraper_types: Optional[list[str]] = None,
        state_code: Optional[str] = None,
        dry_run: bool = False
    ) -> dict:
        """Run scrapers synchronously and return results."""
        return self._run(scraper_types, state_code, dry_run)

    def _run(
        self,
        scraper_types: Optional[list[str]] = None,
        state_code: Optional[str] = None,
        dry_run: bool = False
    ) -> dict:
        """Internal run method."""
        # Reset state
        self._stop_requested.clear()
        self.progress = ScraperProgress(
            status=ScraperStatus.RUNNING,
            started_at=datetime.now(timezone.utc)
        )

        # Default to all scraper types
        if not scraper_types:
            scraper_types = ["admin_monitor", "youtube_channel", "rss_feed"]

        db = SessionLocal()

        try:
            # Get state filter if specified
            state = None
            if state_code:
                state = db.query(State).filter(State.code == state_code.upper()).first()
                if not state:
                    raise ValueError(f"State not found: {state_code}")

            # Count total sources
            total_sources = 0
            for scraper_type in scraper_types:
                query = db.query(Source).filter(
                    Source.source_type == scraper_type,
                    Source.enabled == True
                )
                if state:
                    query = query.filter(Source.state_id == state.id)
                total_sources += query.count()

            self.progress.total_sources = total_sources

            # Run each scraper type
            for scraper_type in scraper_types:
                if self._stop_requested.is_set():
                    break

                self._run_scraper_type(db, scraper_type, state, dry_run)

            # Set final status
            if self._stop_requested.is_set():
                self.progress.status = ScraperStatus.IDLE
                logger.info("Scraper stopped by user request")
            elif self.progress.errors:
                self.progress.status = ScraperStatus.COMPLETED
                logger.warning(f"Scraper completed with {len(self.progress.errors)} errors")
            else:
                self.progress.status = ScraperStatus.COMPLETED
                logger.info("Scraper completed successfully")

        except Exception as e:
            self.progress.status = ScraperStatus.ERROR
            self.progress.add_error("orchestrator", str(e))
            logger.error(f"Orchestrator error: {e}")

        finally:
            self.progress.finished_at = datetime.now(timezone.utc)
            db.close()

        return self.progress.to_dict()

    def _run_scraper_type(
        self,
        db,
        scraper_type: str,
        state: Optional[State],
        dry_run: bool
    ):
        """Run all sources for a specific scraper type."""
        self.progress.current_scraper_type = scraper_type

        # Initialize scraper results
        self.progress.scraper_results[scraper_type] = {
            "sources_scraped": 0,
            "items_found": 0,
            "new_hearings": 0,
            "existing_hearings": 0,
            "errors": 0
        }

        # Get sources for this type
        query = db.query(Source).filter(
            Source.source_type == scraper_type,
            Source.enabled == True
        )
        if state:
            query = query.filter(Source.state_id == state.id)

        sources = query.all()

        if not sources:
            logger.info(f"No {scraper_type} sources found")
            return

        logger.info(f"Starting {scraper_type} scraper with {len(sources)} sources")

        for source in sources:
            if self._stop_requested.is_set():
                break

            self.progress.current_source_name = source.name
            self.progress.current_source_index += 1

            try:
                results = self._scrape_source(db, source, scraper_type, dry_run)

                # Update progress
                self.progress.sources_completed += 1
                self.progress.items_found += results.get("items_found", 0)
                self.progress.new_hearings += results.get("new_hearings", 0)
                self.progress.existing_hearings += results.get("existing_hearings", 0)

                # Update per-scraper results
                sr = self.progress.scraper_results[scraper_type]
                sr["sources_scraped"] += 1
                sr["items_found"] += results.get("items_found", 0)
                sr["new_hearings"] += results.get("new_hearings", 0)
                sr["existing_hearings"] += results.get("existing_hearings", 0)

                if results.get("errors"):
                    sr["errors"] += len(results["errors"])
                    for err in results["errors"]:
                        self.progress.add_error(source.name, err)

            except Exception as e:
                self.progress.add_error(source.name, str(e))
                self.progress.scraper_results[scraper_type]["errors"] += 1
                logger.error(f"Error scraping {source.name}: {e}")

    def _scrape_source(self, db, source: Source, scraper_type: str, dry_run: bool) -> dict:
        """Scrape a single source using the appropriate scraper."""

        if scraper_type == "admin_monitor":
            return self._scrape_adminmonitor(db, source, dry_run)
        elif scraper_type == "youtube_channel":
            return self._scrape_youtube(db, source, dry_run)
        elif scraper_type == "rss_feed":
            return self._scrape_rss(db, source, dry_run)
        else:
            raise ValueError(f"Unknown scraper type: {scraper_type}")

    def _scrape_adminmonitor(self, db, source: Source, dry_run: bool) -> dict:
        """Scrape an AdminMonitor source."""
        from scripts.scrapers.adminmonitor import AdminMonitorScraper, parse_adminmonitor_url

        results = {
            "items_found": 0,
            "new_hearings": 0,
            "existing_hearings": 0,
            "errors": []
        }

        try:
            state_code, agency_code = parse_adminmonitor_url(source.url)
            scraper = AdminMonitorScraper(state_code, agency_code)

            logger.info(f"Scraping AdminMonitor: {source.name}")
            meetings = scraper.scrape_all_meetings(include_future=False, fetch_details=True)
            results["items_found"] = len(meetings)

            for meeting in meetings:
                if self._stop_requested.is_set():
                    break

                existing = db.query(Hearing).filter(
                    Hearing.source_id == source.id,
                    Hearing.external_id == meeting.external_id
                ).first()

                if existing:
                    results["existing_hearings"] += 1
                    continue

                hearing = Hearing(
                    source_id=source.id,
                    state_id=source.state_id,
                    external_id=meeting.external_id,
                    title=meeting.title,
                    description=meeting.description,
                    hearing_date=meeting.meeting_date,
                    hearing_type=meeting.meeting_type,
                    source_url=meeting.source_url,
                    video_url=meeting.video_url,
                    duration_seconds=meeting.duration_seconds,
                    status="discovered",
                )

                if not dry_run:
                    db.add(hearing)

                results["new_hearings"] += 1

            self._update_source_status(db, source, results, meetings, dry_run, date_attr="meeting_date")

        except Exception as e:
            results["errors"].append(str(e))
            self._mark_source_error(db, source, str(e), dry_run)

        return results

    def _scrape_youtube(self, db, source: Source, dry_run: bool) -> dict:
        """Scrape a YouTube channel source."""
        from scripts.scrapers.youtube import YouTubeScraper, is_hearing_video

        results = {
            "items_found": 0,
            "new_hearings": 0,
            "existing_hearings": 0,
            "errors": []
        }

        try:
            scraper = YouTubeScraper(source.url)

            logger.info(f"Scraping YouTube: {source.name}")
            videos = scraper.fetch_videos(max_videos=1500)
            results["items_found"] = len(videos)

            # Filter for hearing content
            videos = [v for v in videos if is_hearing_video(v)]

            # Apply source-specific title filter if configured
            config = source.config_json or {}
            title_filter = config.get('title_filter')
            if title_filter:
                title_filter_lower = title_filter.lower()
                videos = [v for v in videos if title_filter_lower in v.title.lower()]
                logger.info(f"Title filter '{title_filter}' applied: {len(videos)} videos remaining")

            for video in videos:
                if self._stop_requested.is_set():
                    break

                existing = db.query(Hearing).filter(
                    Hearing.source_id == source.id,
                    Hearing.external_id == video.external_id
                ).first()

                if existing:
                    results["existing_hearings"] += 1
                    continue

                hearing_type = self._infer_youtube_hearing_type(video.title)

                hearing = Hearing(
                    source_id=source.id,
                    state_id=source.state_id,
                    external_id=video.external_id,
                    title=video.title,
                    description=video.description,
                    hearing_date=video.upload_date,
                    hearing_type=hearing_type,
                    source_url=source.url,
                    video_url=video.video_url,
                    duration_seconds=video.duration_seconds,
                    status="discovered",
                )

                if not dry_run:
                    db.add(hearing)

                results["new_hearings"] += 1

            self._update_source_status(db, source, results, videos, dry_run, date_attr="upload_date")

        except Exception as e:
            results["errors"].append(str(e))
            self._mark_source_error(db, source, str(e), dry_run)

        return results

    def _scrape_rss(self, db, source: Source, dry_run: bool) -> dict:
        """Scrape an RSS feed source."""
        from scripts.scrapers.rss import create_scraper, infer_hearing_type

        results = {
            "items_found": 0,
            "new_hearings": 0,
            "existing_hearings": 0,
            "errors": []
        }

        try:
            scraper = create_scraper(source.url)

            logger.info(f"Scraping RSS: {source.name}")
            items = scraper.fetch_items()
            results["items_found"] = len(items)

            for item in items:
                if self._stop_requested.is_set():
                    break

                existing = db.query(Hearing).filter(
                    Hearing.source_id == source.id,
                    Hearing.external_id == item.external_id
                ).first()

                if existing:
                    results["existing_hearings"] += 1
                    continue

                hearing_type = infer_hearing_type(item.title, item.categories)

                hearing = Hearing(
                    source_id=source.id,
                    state_id=source.state_id,
                    external_id=item.external_id,
                    title=item.title,
                    description=item.description,
                    hearing_date=item.pub_date,
                    hearing_type=hearing_type,
                    source_url=item.link,
                    video_url=item.video_url,
                    duration_seconds=item.duration_seconds,
                    status="discovered",
                )

                if not dry_run:
                    db.add(hearing)

                results["new_hearings"] += 1

            self._update_source_status(db, source, results, items, dry_run, date_attr="pub_date")

        except Exception as e:
            results["errors"].append(str(e))
            self._mark_source_error(db, source, str(e), dry_run)

        return results

    def _infer_youtube_hearing_type(self, title: str) -> str:
        """Infer hearing type from YouTube video title."""
        title_lower = title.lower()

        type_patterns = [
            ("Voting Meeting", ["voting meeting", "business meeting"]),
            ("Public Hearing", ["public hearing", "public comment"]),
            ("Evidentiary Hearing", ["evidentiary hearing", "evidentiary"]),
            ("Workshop", ["workshop", "technical conference"]),
            ("Rate Case", ["rate case", "rate hearing", "rate increase"]),
            ("IRP Hearing", ["irp", "integrated resource plan", "resource plan"]),
            ("Oral Argument", ["oral argument"]),
            ("Commission Meeting", ["commission meeting", "regular meeting", "open meeting"]),
            ("Prehearing Conference", ["prehearing", "pre-hearing"]),
            ("Staff Conference", ["staff conference", "staff meeting"]),
        ]

        for hearing_type, keywords in type_patterns:
            if any(kw in title_lower for kw in keywords):
                return hearing_type

        return "Hearing"

    def _update_source_status(self, db, source: Source, results: dict, items: list, dry_run: bool, date_attr: str):
        """Update source status after successful scrape."""
        if dry_run:
            return

        source.last_checked_at = datetime.now(timezone.utc)
        source.status = "active"
        source.error_message = None

        if results["new_hearings"] > 0 and items:
            try:
                latest = max(
                    (i for i in items if getattr(i, date_attr, None)),
                    key=lambda i: getattr(i, date_attr),
                    default=None
                )
                if latest:
                    date_val = getattr(latest, date_attr)
                    if hasattr(date_val, 'date'):
                        date_val = date_val.date()
                    source.last_hearing_at = datetime.combine(
                        date_val,
                        datetime.min.time(),
                        tzinfo=timezone.utc
                    )
            except (ValueError, TypeError):
                pass

        db.commit()

    def _mark_source_error(self, db, source: Source, error: str, dry_run: bool):
        """Mark source as having an error."""
        if dry_run:
            return

        source.status = "error"
        source.error_message = error[:500]
        source.last_checked_at = datetime.now(timezone.utc)
        db.commit()


# Global orchestrator instance for API access
_orchestrator: Optional[ScraperOrchestrator] = None


def get_orchestrator() -> ScraperOrchestrator:
    """Get or create the global orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = ScraperOrchestrator()
    return _orchestrator


def main():
    parser = argparse.ArgumentParser(description="Run all scrapers")
    parser.add_argument(
        "--type",
        choices=["admin_monitor", "youtube_channel", "rss_feed"],
        action="append",
        dest="types",
        help="Scraper type(s) to run (can specify multiple)"
    )
    parser.add_argument("--state", help="State code to filter sources (e.g., CA, TX)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without saving")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    orchestrator = get_orchestrator()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\nStopping scraper (will finish current source)...")
        orchestrator.request_stop()

    signal.signal(signal.SIGINT, signal_handler)

    # Run synchronously
    results = orchestrator.run(
        scraper_types=args.types,
        state_code=args.state,
        dry_run=args.dry_run
    )

    # Print summary
    print("\n" + "=" * 70)
    print("SCRAPE SUMMARY")
    print("=" * 70)
    print(f"Status:             {results['status']}")
    print(f"Sources completed:  {results['sources_completed']} / {results['total_sources']}")
    print(f"Items found:        {results['items_found']}")
    print(f"New hearings:       {results['new_hearings']}")
    print(f"Existing hearings:  {results['existing_hearings']}")
    print(f"Errors:             {results['error_count']}")

    if results.get("scraper_results"):
        print("\nPer-scraper breakdown:")
        for scraper_type, sr in results["scraper_results"].items():
            print(f"\n  {scraper_type}:")
            print(f"    Sources:    {sr['sources_scraped']}")
            print(f"    Items:      {sr['items_found']}")
            print(f"    New:        {sr['new_hearings']}")
            print(f"    Existing:   {sr['existing_hearings']}")
            print(f"    Errors:     {sr['errors']}")

    if args.dry_run:
        print("\n[DRY RUN - No changes saved to database]")

    if results["errors"]:
        print("\nRecent errors:")
        for err in results["errors"][-5:]:
            print(f"  [{err['timestamp'][:19]}] {err['source']}: {err['error'][:80]}")

    return 0 if results["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
