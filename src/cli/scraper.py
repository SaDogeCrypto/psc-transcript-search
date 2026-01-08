"""Scraper CLI commands."""

from datetime import datetime, timedelta
from typing import Optional

import click

from src.core.config import get_settings
from src.core.database import get_db_session
from src.states.registry import StateRegistry


@click.group()
def scraper():
    """Scraper commands."""
    pass


@scraper.command("list")
@click.option("--state", "-s", help="Filter by state code (e.g., FL)")
def list_scrapers(state: Optional[str]):
    """List available scrapers."""
    if state:
        scrapers = StateRegistry.get_state_scrapers(state.upper())
        if not scrapers:
            click.echo(f"No scrapers found for state: {state}")
            return
        click.echo(f"\nScrapers for {state.upper()}:")
        for name in scrapers:
            click.echo(f"  - {name}")
    else:
        all_scrapers = StateRegistry.get_all_scrapers()
        if not all_scrapers:
            click.echo("No scrapers registered.")
            return
        click.echo("\nRegistered scrapers:")
        for state_code, scrapers in all_scrapers.items():
            metadata = StateRegistry.get_metadata(state_code)
            state_name = metadata.get("full_name", state_code) if metadata else state_code
            click.echo(f"\n  {state_name} ({state_code}):")
            for name in scrapers:
                click.echo(f"    - {name}")


@scraper.command("run")
@click.argument("state")
@click.argument("scraper_name")
@click.option("--days", "-d", default=30, help="Number of days to look back")
@click.option("--docket", help="Specific docket number to scrape")
@click.option("--dry-run", is_flag=True, help="Show what would be scraped without saving")
def run_scraper(state: str, scraper_name: str, days: int, docket: Optional[str], dry_run: bool):
    """Run a specific scraper.

    STATE: State code (e.g., FL)
    SCRAPER_NAME: Name of the scraper to run
    """
    state = state.upper()

    scraper_class = StateRegistry.get_scraper(state, scraper_name)
    if not scraper_class:
        click.echo(f"Scraper not found: {state}/{scraper_name}")
        available = StateRegistry.get_state_scrapers(state)
        if available:
            click.echo(f"Available scrapers for {state}: {', '.join(available)}")
        return

    settings = get_settings()

    with get_db_session() as session:
        scraper_instance = scraper_class(session, settings)

        click.echo(f"Running {scraper_name} scraper for {state}...")

        if docket:
            click.echo(f"  Docket: {docket}")
            results = scraper_instance.scrape_docket(docket)
        else:
            start_date = datetime.now() - timedelta(days=days)
            click.echo(f"  Looking back {days} days (since {start_date.date()})")
            results = scraper_instance.scrape(start_date=start_date)

        if dry_run:
            click.echo(f"\n[DRY RUN] Would process {len(results)} items")
            for i, item in enumerate(results[:5]):
                click.echo(f"  {i+1}. {item}")
            if len(results) > 5:
                click.echo(f"  ... and {len(results) - 5} more")
        else:
            click.echo(f"\nProcessed {len(results)} items")


@scraper.command("run-all")
@click.argument("state")
@click.option("--days", "-d", default=30, help="Number of days to look back")
@click.option("--dry-run", is_flag=True, help="Show what would be scraped without saving")
def run_all_scrapers(state: str, days: int, dry_run: bool):
    """Run all scrapers for a state.

    STATE: State code (e.g., FL)
    """
    state = state.upper()

    scrapers = StateRegistry.get_state_scrapers(state)
    if not scrapers:
        click.echo(f"No scrapers found for state: {state}")
        return

    settings = get_settings()

    with get_db_session() as session:
        for scraper_name in scrapers:
            scraper_class = StateRegistry.get_scraper(state, scraper_name)
            if not scraper_class:
                continue

            scraper_instance = scraper_class(session, settings)

            click.echo(f"\nRunning {scraper_name}...")

            try:
                start_date = datetime.now() - timedelta(days=days)
                results = scraper_instance.scrape(start_date=start_date)

                if dry_run:
                    click.echo(f"  [DRY RUN] Would process {len(results)} items")
                else:
                    click.echo(f"  Processed {len(results)} items")
            except Exception as e:
                click.echo(f"  Error: {e}", err=True)


@scraper.command("states")
def list_states():
    """List available states."""
    states = StateRegistry.get_available_states()
    if not states:
        click.echo("No states registered.")
        return

    click.echo("\nAvailable states:")
    for state_code in sorted(states):
        metadata = StateRegistry.get_metadata(state_code)
        if metadata:
            click.echo(f"  {state_code}: {metadata.get('full_name', state_code)}")
            click.echo(f"       Commission: {metadata.get('commission_name', 'N/A')}")
        else:
            click.echo(f"  {state_code}")
