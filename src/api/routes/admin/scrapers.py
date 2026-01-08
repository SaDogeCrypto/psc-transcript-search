"""
Scraper admin routes.

Provides endpoints to run data scrapers for each state.
"""

import logging
import time
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from src.api.dependencies import get_db, require_admin
from src.api.schemas.scraper import (
    ScraperRunRequest,
    ScraperResultResponse,
    ScraperListResponse,
    ScraperStatusResponse,
)
from src.states.registry import StateRegistry

logger = logging.getLogger(__name__)
router = APIRouter()

# Store for tracking scraper runs
_scraper_runs = {}


@router.get("", response_model=ScraperListResponse)
def list_scrapers(
    _admin: bool = Depends(require_admin),
):
    """
    List all available scrapers by state.
    """
    return ScraperListResponse(
        scrapers=StateRegistry.get_all_scrapers()
    )


@router.post("/run", response_model=ScraperResultResponse)
def run_scraper(
    request: ScraperRunRequest,
    db: Session = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """
    Run a scraper synchronously.

    Florida scrapers:
    - clerk_office: Scrape dockets from ClerkOffice API
    - thunderstone: Scrape documents from Thunderstone search
    - rss_hearings: Scrape hearings from YouTube RSS feed
    """
    # Get scraper class
    scraper_class = StateRegistry.get_scraper(request.state_code, request.scraper)

    if not scraper_class:
        available = StateRegistry.get_state_scrapers(request.state_code)
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scraper: {request.scraper}. Available for {request.state_code}: {available}"
        )

    # Create scraper instance
    scraper = scraper_class(db)

    # Validate config
    is_valid, error = scraper.validate_config()
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail=f"Scraper configuration error: {error}"
        )

    # Build kwargs based on scraper
    kwargs = {"limit": request.limit}

    if request.year:
        kwargs["year"] = request.year
    if request.docket_number:
        kwargs["docket_number"] = request.docket_number
    if request.profile:
        kwargs["profile"] = request.profile
    if request.query:
        kwargs["query"] = request.query

    # Run scraper
    start_time = time.time()
    logger.info(f"Running scraper {request.state_code}/{request.scraper}")

    try:
        result = scraper.scrape(**kwargs)

        duration = time.time() - start_time

        # Store result
        run_key = f"{request.state_code}_{request.scraper}"
        _scraper_runs[run_key] = {
            "last_run": datetime.utcnow(),
            "result": result,
            "duration": duration,
        }

        return ScraperResultResponse(
            success=result.success,
            scraper=request.scraper,
            state_code=request.state_code,
            items_found=result.items_found,
            items_created=result.items_created,
            items_updated=result.items_updated,
            errors=result.errors,
            duration_seconds=duration,
        )

    except Exception as e:
        logger.exception(f"Scraper {request.scraper} failed")
        raise HTTPException(
            status_code=500,
            detail=f"Scraper failed: {str(e)}"
        )


@router.post("/run-async")
async def run_scraper_async(
    request: ScraperRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """
    Run a scraper in the background.

    Returns immediately, use /status to check progress.
    """
    # Validate scraper exists
    scraper_class = StateRegistry.get_scraper(request.state_code, request.scraper)
    if not scraper_class:
        available = StateRegistry.get_state_scrapers(request.state_code)
        raise HTTPException(
            status_code=400,
            detail=f"Unknown scraper: {request.scraper}. Available: {available}"
        )

    run_key = f"{request.state_code}_{request.scraper}"
    _scraper_runs[run_key] = {
        "status": "queued",
        "started_at": datetime.utcnow(),
    }

    # Queue background task
    async def run_in_background():
        from src.core.database import SessionLocal
        db_session = SessionLocal()
        try:
            scraper = scraper_class(db_session)
            kwargs = {"limit": request.limit}
            if request.year:
                kwargs["year"] = request.year
            if request.docket_number:
                kwargs["docket_number"] = request.docket_number
            if request.profile:
                kwargs["profile"] = request.profile

            start_time = time.time()
            result = scraper.scrape(**kwargs)

            _scraper_runs[run_key] = {
                "status": "completed",
                "last_run": datetime.utcnow(),
                "result": result,
                "duration": time.time() - start_time,
            }
        except Exception as e:
            logger.exception(f"Background scraper {run_key} failed")
            _scraper_runs[run_key] = {
                "status": "failed",
                "error": str(e),
                "completed_at": datetime.utcnow(),
            }
        finally:
            db_session.close()

    background_tasks.add_task(run_in_background)

    return {
        "status": "queued",
        "scraper": request.scraper,
        "state_code": request.state_code,
    }


@router.get("/status/{state_code}/{scraper}", response_model=ScraperStatusResponse)
def get_scraper_status(
    state_code: str,
    scraper: str,
    db: Session = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """
    Get status of a scraper including last run info.
    """
    # Check if scraper exists
    scraper_class = StateRegistry.get_scraper(state_code, scraper)
    if not scraper_class:
        raise HTTPException(status_code=404, detail="Scraper not found")

    # Check configuration
    scraper_instance = scraper_class(db)
    is_configured, config_error = scraper_instance.validate_config()

    # Get last run info
    run_key = f"{state_code}_{scraper}"
    run_info = _scraper_runs.get(run_key, {})

    last_result = None
    if run_info.get("result"):
        r = run_info["result"]
        last_result = ScraperResultResponse(
            success=r.success,
            scraper=scraper,
            state_code=state_code,
            items_found=r.items_found,
            items_created=r.items_created,
            items_updated=r.items_updated,
            errors=r.errors,
            duration_seconds=run_info.get("duration"),
        )

    return ScraperStatusResponse(
        scraper=scraper,
        state_code=state_code,
        last_run=run_info.get("last_run"),
        last_result=last_result,
        is_configured=is_configured,
        config_error=config_error if not is_configured else None,
    )


@router.get("/states")
def list_states(
    _admin: bool = Depends(require_admin),
):
    """
    List all registered states with their metadata.
    """
    states = StateRegistry.get_available_states()

    return {
        "states": [
            {
                "code": state,
                "metadata": StateRegistry.get_metadata(state),
                "scrapers": StateRegistry.get_state_scrapers(state),
                "stages": StateRegistry.get_state_stages(state),
            }
            for state in states
        ]
    }


@router.get("/stats")
def get_scraper_stats(
    state_code: Optional[str] = None,
    db: Session = Depends(get_db),
    _admin: bool = Depends(require_admin),
):
    """
    Get data statistics from scrapers.

    Returns counts of dockets, documents, and hearings.
    """
    from sqlalchemy import func
    from src.core.models.docket import Docket
    from src.core.models.document import Document
    from src.core.models.hearing import Hearing

    stats = {}

    # Get states to report on
    if state_code:
        states = [state_code.upper()]
    else:
        states = StateRegistry.get_available_states()

    for state in states:
        docket_count = db.query(func.count(Docket.id)).filter(
            Docket.state_code == state
        ).scalar()

        document_count = db.query(func.count(Document.id)).filter(
            Document.state_code == state
        ).scalar()

        hearing_count = db.query(func.count(Hearing.id)).filter(
            Hearing.state_code == state
        ).scalar()

        stats[state] = {
            "dockets": docket_count,
            "documents": document_count,
            "hearings": hearing_count,
        }

    return {
        "stats": stats,
        "total": {
            "dockets": sum(s["dockets"] for s in stats.values()),
            "documents": sum(s["documents"] for s in stats.values()),
            "hearings": sum(s["hearings"] for s in stats.values()),
        }
    }
