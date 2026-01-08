"""Pipeline CLI commands."""

from typing import Optional
from uuid import UUID

import click

from src.core.config import get_settings
from src.core.database import get_db_session
from src.core.models.hearing import Hearing


@click.group()
def pipeline():
    """Pipeline commands for processing hearings."""
    pass


@pipeline.command("status")
@click.option("--state", "-s", help="Filter by state code")
def show_status(state: Optional[str]):
    """Show pipeline status and hearing counts by status."""
    from sqlalchemy import select, func

    with get_db_session() as session:
        query = select(
            Hearing.transcript_status,
            func.count(Hearing.id)
        ).group_by(Hearing.transcript_status)

        if state:
            query = query.where(Hearing.state_code == state.upper())

        result = session.execute(query)
        counts = dict(result.fetchall())

        total = sum(counts.values())

        click.echo("\nPipeline Status:")
        if state:
            click.echo(f"  State: {state.upper()}")
        click.echo(f"  Total hearings: {total}")
        click.echo("\n  By status:")

        status_order = ["pending", "downloading", "transcribing", "transcribed", "analyzing", "analyzed", "error"]
        for status in status_order:
            count = counts.get(status, 0)
            if count > 0:
                pct = (count / total * 100) if total > 0 else 0
                click.echo(f"    {status}: {count} ({pct:.1f}%)")


@pipeline.command("transcribe")
@click.option("--hearing-id", "-h", help="Specific hearing ID to transcribe")
@click.option("--state", "-s", help="Filter by state code")
@click.option("--limit", "-l", default=10, help="Maximum hearings to process")
@click.option("--dry-run", is_flag=True, help="Show what would be transcribed")
def transcribe(hearing_id: Optional[str], state: Optional[str], limit: int, dry_run: bool):
    """Transcribe pending hearings."""
    from sqlalchemy import select
    from src.core.pipeline.orchestrator import PipelineOrchestrator

    settings = get_settings()

    with get_db_session() as session:
        orchestrator = PipelineOrchestrator(session, settings)

        if hearing_id:
            click.echo(f"Transcribing hearing: {hearing_id}")
            hearing = session.get(Hearing, UUID(hearing_id))
            if not hearing:
                click.echo(f"Hearing not found: {hearing_id}")
                return

            if dry_run:
                click.echo(f"[DRY RUN] Would transcribe: {hearing.title or hearing.id}")
                return

            result = orchestrator.run_stage("transcribe", hearing)
            click.echo(f"Result: {result.status}")
            if result.error:
                click.echo(f"Error: {result.error}")
        else:
            click.echo(f"Finding pending hearings to transcribe (limit: {limit})...")

            query = select(Hearing).where(
                Hearing.transcript_status == "pending"
            ).limit(limit)

            if state:
                query = query.where(Hearing.state_code == state.upper())

            result = session.execute(query)
            hearings = result.scalars().all()

            if not hearings:
                click.echo("No pending hearings found.")
                return

            click.echo(f"Found {len(hearings)} hearings to transcribe")

            if dry_run:
                click.echo("\n[DRY RUN] Would transcribe:")
                for h in hearings:
                    click.echo(f"  - {h.title or h.id}")
                return

            results = orchestrator.run_batch("transcribe", hearings)

            success = sum(1 for r in results if r.status == "success")
            click.echo(f"\nCompleted: {success}/{len(results)} successful")


@pipeline.command("analyze")
@click.option("--hearing-id", "-h", help="Specific hearing ID to analyze")
@click.option("--state", "-s", help="Filter by state code")
@click.option("--limit", "-l", default=10, help="Maximum hearings to process")
@click.option("--dry-run", is_flag=True, help="Show what would be analyzed")
def analyze(hearing_id: Optional[str], state: Optional[str], limit: int, dry_run: bool):
    """Analyze transcribed hearings."""
    from sqlalchemy import select
    from src.core.pipeline.orchestrator import PipelineOrchestrator

    settings = get_settings()

    with get_db_session() as session:
        orchestrator = PipelineOrchestrator(session, settings)

        if hearing_id:
            click.echo(f"Analyzing hearing: {hearing_id}")
            hearing = session.get(Hearing, UUID(hearing_id))
            if not hearing:
                click.echo(f"Hearing not found: {hearing_id}")
                return

            if dry_run:
                click.echo(f"[DRY RUN] Would analyze: {hearing.title or hearing.id}")
                return

            result = orchestrator.run_stage("analyze", hearing)
            click.echo(f"Result: {result.status}")
            if result.error:
                click.echo(f"Error: {result.error}")
        else:
            click.echo(f"Finding transcribed hearings to analyze (limit: {limit})...")

            query = select(Hearing).where(
                Hearing.transcript_status == "transcribed"
            ).limit(limit)

            if state:
                query = query.where(Hearing.state_code == state.upper())

            result = session.execute(query)
            hearings = result.scalars().all()

            if not hearings:
                click.echo("No transcribed hearings found.")
                return

            click.echo(f"Found {len(hearings)} hearings to analyze")

            if dry_run:
                click.echo("\n[DRY RUN] Would analyze:")
                for h in hearings:
                    click.echo(f"  - {h.title or h.id}")
                return

            results = orchestrator.run_batch("analyze", hearings)

            success = sum(1 for r in results if r.status == "success")
            click.echo(f"\nCompleted: {success}/{len(results)} successful")


@pipeline.command("process")
@click.option("--state", "-s", help="Filter by state code")
@click.option("--limit", "-l", default=10, help="Maximum hearings to process")
@click.option("--dry-run", is_flag=True, help="Show what would be processed")
def process_all(state: Optional[str], limit: int, dry_run: bool):
    """Run full pipeline (transcribe + analyze) on pending hearings."""
    from sqlalchemy import select
    from src.core.pipeline.orchestrator import PipelineOrchestrator

    settings = get_settings()

    with get_db_session() as session:
        orchestrator = PipelineOrchestrator(session, settings)

        click.echo(f"Finding pending hearings (limit: {limit})...")

        query = select(Hearing).where(
            Hearing.transcript_status == "pending"
        ).limit(limit)

        if state:
            query = query.where(Hearing.state_code == state.upper())

        result = session.execute(query)
        hearings = result.scalars().all()

        if not hearings:
            click.echo("No pending hearings found.")
            return

        click.echo(f"Found {len(hearings)} hearings to process")

        if dry_run:
            click.echo("\n[DRY RUN] Would process:")
            for h in hearings:
                click.echo(f"  - {h.title or h.id}")
            return

        for hearing in hearings:
            click.echo(f"\nProcessing: {hearing.title or hearing.id}")

            # Transcribe
            click.echo("  Transcribing...")
            result = orchestrator.run_stage("transcribe", hearing)
            if result.status != "success":
                click.echo(f"  Transcription failed: {result.error}")
                continue
            click.echo("  Transcription complete")

            # Analyze
            click.echo("  Analyzing...")
            result = orchestrator.run_stage("analyze", hearing)
            if result.status != "success":
                click.echo(f"  Analysis failed: {result.error}")
                continue
            click.echo("  Analysis complete")

        click.echo("\nPipeline complete")


@pipeline.command("retry-errors")
@click.option("--state", "-s", help="Filter by state code")
@click.option("--limit", "-l", default=10, help="Maximum hearings to retry")
def retry_errors(state: Optional[str], limit: int):
    """Retry hearings that failed processing."""
    from sqlalchemy import select

    with get_db_session() as session:
        query = select(Hearing).where(
            Hearing.transcript_status == "error"
        ).limit(limit)

        if state:
            query = query.where(Hearing.state_code == state.upper())

        result = session.execute(query)
        hearings = result.scalars().all()

        if not hearings:
            click.echo("No failed hearings found.")
            return

        click.echo(f"Found {len(hearings)} failed hearings to retry")

        # Reset status to pending
        for hearing in hearings:
            hearing.transcript_status = "pending"

        click.echo("Reset to pending. Run 'pipeline process' to retry.")
