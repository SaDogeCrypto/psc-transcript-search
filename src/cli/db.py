"""Database CLI commands."""

import click

from src.core.config import get_settings
from src.core.database import engine, get_db_session
from src.core.models.base import Base


@click.group()
def db():
    """Database management commands."""
    pass


@db.command("init")
@click.option("--drop", is_flag=True, help="Drop existing tables first")
def init_db(drop: bool):
    """Initialize the database schema."""
    # Import all models so they're registered
    from src.core.models import docket, document, hearing, transcript, analysis, entity
    from src.states.florida.models import docket as fl_docket, document as fl_document, hearing as fl_hearing

    if drop:
        click.echo("Dropping existing tables...")
        Base.metadata.drop_all(bind=engine)

    click.echo("Creating tables...")
    Base.metadata.create_all(bind=engine)
    click.echo("Database initialized.")


@db.command("info")
def db_info():
    """Show database connection info."""
    settings = get_settings()

    # Mask password in connection string
    db_url = str(settings.database_url)
    if "@" in db_url:
        # Format: postgresql://user:pass@host/db
        parts = db_url.split("@")
        prefix = parts[0].rsplit(":", 1)[0]  # Remove password
        db_url = f"{prefix}:****@{parts[1]}"

    click.echo(f"\nDatabase URL: {db_url}")
    click.echo(f"Environment: {settings.log_level}")


@db.command("stats")
def db_stats():
    """Show database statistics."""
    from sqlalchemy import select, func
    from src.core.models.docket import Docket
    from src.core.models.document import Document
    from src.core.models.hearing import Hearing

    with get_db_session() as session:
        # Count records
        docket_count = session.scalar(select(func.count(Docket.id)))
        document_count = session.scalar(select(func.count(Document.id)))
        hearing_count = session.scalar(select(func.count(Hearing.id)))

        click.echo("\nDatabase Statistics:")
        click.echo(f"  Dockets: {docket_count}")
        click.echo(f"  Documents: {document_count}")
        click.echo(f"  Hearings: {hearing_count}")

        # Hearings by state
        result = session.execute(
            select(Hearing.state_code, func.count(Hearing.id))
            .group_by(Hearing.state_code)
        )
        by_state = dict(result.fetchall())

        if by_state:
            click.echo("\n  Hearings by state:")
            for state, count in sorted(by_state.items()):
                click.echo(f"    {state}: {count}")

        # Hearings by status
        result = session.execute(
            select(Hearing.transcript_status, func.count(Hearing.id))
            .group_by(Hearing.transcript_status)
        )
        by_status = dict(result.fetchall())

        if by_status:
            click.echo("\n  Hearings by status:")
            for status, count in sorted(by_status.items()):
                click.echo(f"    {status}: {count}")


@db.command("migrate")
@click.option("--revision", "-r", default="head", help="Revision to migrate to")
def migrate(revision: str):
    """Run database migrations."""
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, revision)
    click.echo(f"Migrated to: {revision}")


@db.command("revision")
@click.option("--message", "-m", required=True, help="Revision message")
@click.option("--autogenerate", is_flag=True, help="Autogenerate from model changes")
def create_revision(message: str, autogenerate: bool):
    """Create a new migration revision."""
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    command.revision(alembic_cfg, message=message, autogenerate=autogenerate)
    click.echo(f"Created revision: {message}")
