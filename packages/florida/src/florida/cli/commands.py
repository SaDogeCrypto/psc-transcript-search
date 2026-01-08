"""
Florida PSC CLI commands.

Provides command-line interface for Florida PSC operations:
- Docket sync from ClerkOffice API
- Document indexing from Thunderstone
- Pipeline execution
- Status and statistics
"""

import click
import logging
from datetime import datetime
from typing import Optional

from florida.config import get_config
from florida.models import get_db, init_db

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False):
    """Configure logging for CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


@click.group()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.pass_context
def cli(ctx, verbose):
    """Florida PSC command-line tools."""
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    setup_logging(verbose)


@cli.command()
@click.option('--year', '-y', type=int, help='Filter by year')
@click.option('--status', '-s', type=click.Choice(['open', 'closed']), help='Filter by status')
@click.option('--limit', '-l', type=int, default=1000, help='Maximum dockets to sync')
@click.option('--all-types', is_flag=True, help='Sync all docket types (not just open)')
@click.option('--industries', '-i', multiple=True,
              type=click.Choice(['E', 'G', 'T', 'W', 'X']),
              help='Industries to sync (E=Electric, G=Gas, T=Telecom, W=Water, X=Other)')
@click.pass_context
def sync_dockets(ctx, year, status, limit, all_types, industries):
    """Sync dockets from Florida PSC ClerkOffice API."""
    from florida.pipeline import DocketSyncStage

    click.echo(f"Syncing Florida dockets...")
    if year:
        click.echo(f"  Year filter: {year}")
    if status:
        click.echo(f"  Status filter: {status}")
    if all_types:
        click.echo(f"  Syncing all docket types (open, recent, closed)")
    if industries:
        click.echo(f"  Industries: {', '.join(industries)}")

    db = next(get_db())
    try:
        stage = DocketSyncStage(db)

        def progress(msg):
            click.echo(f"  {msg}")

        # If --all-types, don't filter by status
        effective_status = None if all_types else status

        result = stage.sync_all(
            year=year,
            status=effective_status,
            industries=list(industries) if industries else None,
            limit=limit,
            on_progress=progress
        )

        click.echo("")
        click.echo(f"Sync complete:")
        click.echo(f"  Total scraped: {result.total_scraped}")
        click.echo(f"  New dockets: {result.new_dockets}")
        click.echo(f"  Updated dockets: {result.updated_dockets}")
        click.echo(f"  Duration: {result.duration_seconds:.1f}s")

        if result.errors:
            click.echo(f"  Errors: {len(result.errors)}")
            for err in result.errors[:5]:
                click.echo(f"    - {err}")

    finally:
        db.close()


@cli.command()
@click.option('--mode', '-m', type=click.Choice(['orders', 'search', 'docket', 'filings', 'bulk']),
              default='orders', help='Indexing mode')
@click.option('--query', '-q', type=str, help='Search query (for search mode)')
@click.option('--docket', '-d', type=str, help='Docket number (for docket mode)')
@click.option('--profile', '-p', type=str, default='library',
              help='Thunderstone profile (library, orders, filingsCurrent, etc.)')
@click.option('--years', type=str, help='Years to search, comma-separated (e.g., 2024,2025)')
@click.option('--limit', '-l', type=int, default=100, help='Maximum documents to index')
@click.pass_context
def index_documents(ctx, mode, query, docket, profile, years, limit):
    """Index documents from Florida PSC Thunderstone.

    Modes:
      orders  - Index recent commission orders
      filings - Index current year filings
      search  - Search and index by query
      docket  - Index documents for a specific docket
      bulk    - Index documents for all open dockets
    """
    from florida.pipeline import DocumentSyncStage

    click.echo(f"Indexing Florida documents...")
    click.echo(f"  Mode: {mode}")
    click.echo(f"  Profile: {profile}")

    if mode == 'search' and not query:
        click.echo("Error: --query is required for search mode", err=True)
        return

    if mode == 'docket' and not docket:
        click.echo("Error: --docket is required for docket mode", err=True)
        return

    db = next(get_db())
    try:
        stage = DocumentSyncStage(db)

        def progress(msg):
            click.echo(f"  {msg}")

        if mode == 'orders':
            result = stage.index_recent_orders(limit=limit, on_progress=progress)

        elif mode == 'filings':
            # Search for current year filings
            from datetime import datetime
            year = datetime.now().year
            result = stage.search_and_index(
                query=f'{year}*',
                profile='filingsCurrent',
                limit=limit,
                on_progress=progress
            )

        elif mode == 'search':
            result = stage.search_and_index(
                query=query,
                profile=profile,
                limit=limit,
                on_progress=progress
            )

        elif mode == 'docket':
            result = stage.index_docket_documents(
                docket_number=docket,
                profile=profile,
                limit=limit
            )

        elif mode == 'bulk':
            result = stage.index_open_dockets(
                docs_per_docket=50,
                max_dockets=limit,
                on_progress=progress
            )

        click.echo("")
        click.echo(f"Index complete:")
        click.echo(f"  Total indexed: {result.total_indexed}")
        click.echo(f"  New documents: {result.new_documents}")
        click.echo(f"  Updated documents: {result.updated_documents}")
        if hasattr(result, 'dockets_processed') and result.dockets_processed:
            click.echo(f"  Dockets processed: {result.dockets_processed}")
        click.echo(f"  Duration: {result.duration_seconds:.1f}s")

        if result.errors:
            click.echo(f"  Errors: {len(result.errors)}")
            for err in result.errors[:5]:
                click.echo(f"    - {err}")

    finally:
        db.close()


@cli.command()
@click.option('--year', '-y', type=int, help='Filter docket sync by year')
@click.pass_context
def run_pipeline(ctx, year):
    """Run the full Florida pipeline."""
    from florida.pipeline import FloridaPipelineOrchestrator

    click.echo("Starting Florida pipeline...")

    db = next(get_db())
    try:
        orchestrator = FloridaPipelineOrchestrator(db)

        def progress(msg):
            click.echo(f"  {msg}")

        run = orchestrator.run_full_pipeline(year=year, on_progress=progress)

        click.echo("")
        click.echo(f"Pipeline run {run.run_id} complete:")
        click.echo(f"  Status: {'SUCCESS' if run.success else 'FAILED'}")
        click.echo(f"  Stages run: {', '.join(run.stages_run)}")
        click.echo(f"  Duration: {(run.completed_at - run.started_at).total_seconds():.1f}s")

        if run.results:
            click.echo("  Results:")
            for stage, stats in run.results.items():
                click.echo(f"    {stage}:")
                for key, value in stats.items():
                    click.echo(f"      {key}: {value}")

        if run.errors:
            click.echo(f"  Errors: {len(run.errors)}")
            for err in run.errors[:5]:
                click.echo(f"    - {err}")

    finally:
        db.close()


@cli.command()
@click.pass_context
def status(ctx):
    """Show Florida database status and statistics."""
    from florida.pipeline import FloridaPipelineOrchestrator

    click.echo("Florida PSC Database Status")
    click.echo("=" * 40)

    db = next(get_db())
    try:
        orchestrator = FloridaPipelineOrchestrator(db)
        status = orchestrator.get_pipeline_status()

        # Docket stats
        dockets = status.get('dockets', {})
        click.echo("\nDockets:")
        click.echo(f"  Total: {dockets.get('total', 0)}")
        click.echo(f"  Open: {dockets.get('open', 0)}")
        click.echo(f"  Closed: {dockets.get('closed', 0)}")

        year_range = dockets.get('year_range', {})
        if year_range.get('min') and year_range.get('max'):
            click.echo(f"  Year range: {year_range['min']} - {year_range['max']}")

        by_sector = dockets.get('by_sector', {})
        if by_sector:
            click.echo("  By sector:")
            for sector, count in sorted(by_sector.items()):
                click.echo(f"    {sector}: {count}")

        # Document stats
        documents = status.get('documents', {})
        click.echo("\nDocuments:")
        click.echo(f"  Total: {documents.get('total', 0)}")
        click.echo(f"  Linked to dockets: {documents.get('with_docket', 0)}")
        click.echo(f"  Orphaned: {documents.get('orphaned', 0)}")

        by_type = documents.get('by_type', {})
        if by_type:
            click.echo("  By type:")
            for doc_type, count in sorted(by_type.items(), key=lambda x: -x[1])[:10]:
                click.echo(f"    {doc_type}: {count}")

        # Pipeline stages
        click.echo("\nPipeline stages:")
        for stage in status.get('stages_available', []):
            implemented = stage in status.get('stages_implemented', [])
            marker = '✓' if implemented else '○'
            click.echo(f"  {marker} {stage}")

    finally:
        db.close()


@cli.command()
@click.pass_context
def test_connection(ctx):
    """Test connection to Florida PSC APIs and database."""
    from florida.scrapers import FloridaClerkOfficeScraper, FloridaThunderstoneScraper
    from florida.config import get_config

    config = get_config()

    click.echo("Florida PSC Connection Test")
    click.echo("=" * 40)

    # Show config
    click.echo("\nConfiguration:")
    click.echo(f"  Storage backend: {config.storage_backend}")
    if config.is_azure_db:
        click.echo(f"  Database: Azure PostgreSQL")
    else:
        click.echo(f"  Database: Local PostgreSQL")

    # Test database
    click.echo("\n1. Database:")
    try:
        db = next(get_db())
        from sqlalchemy import text
        result = db.execute(text("SELECT 1")).fetchone()
        click.echo("   ✓ Connected successfully")
        db.close()
    except Exception as e:
        click.echo(f"   ✗ Error: {e}")

    # Test ClerkOffice API
    click.echo("\n2. ClerkOffice API:")
    try:
        scraper = FloridaClerkOfficeScraper()
        if scraper.test_connection():
            click.echo("   ✓ Connected successfully")
        else:
            click.echo("   ✗ Connection failed")
    except Exception as e:
        click.echo(f"   ✗ Error: {e}")

    # Test Thunderstone API
    click.echo("\n3. Thunderstone API:")
    try:
        scraper = FloridaThunderstoneScraper()
        if scraper.test_connection():
            click.echo("   ✓ Connected successfully")
            profiles = scraper.get_profiles()
            click.echo(f"   Available profiles: {len(profiles)}")
            for p in profiles[:5]:
                click.echo(f"     - {p.id}: {p.name}")
        else:
            click.echo("   ✗ Connection failed")
    except Exception as e:
        click.echo(f"   ✗ Error: {e}")

    # Test Azure Blob if configured
    if config.is_azure and config.azure_storage_connection_string:
        click.echo("\n4. Azure Blob Storage:")
        try:
            from azure.storage.blob import BlobServiceClient
            blob_service = BlobServiceClient.from_connection_string(
                config.azure_storage_connection_string
            )
            container = blob_service.get_container_client(config.azure_container_name)
            if container.exists():
                click.echo(f"   ✓ Container '{config.azure_container_name}' exists")
            else:
                click.echo(f"   ! Container '{config.azure_container_name}' does not exist")
        except ImportError:
            click.echo("   ! azure-storage-blob not installed")
        except Exception as e:
            click.echo(f"   ✗ Error: {e}")


@cli.command()
@click.pass_context
def init_database(ctx):
    """Initialize Florida database tables."""
    click.echo("Initializing Florida database...")

    try:
        init_db()
        click.echo("  ✓ Database initialized successfully")
    except Exception as e:
        click.echo(f"  ✗ Error: {e}")


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == '__main__':
    main()
