"""Main CLI entry point."""

import click

from src.cli.scraper import scraper
from src.cli.pipeline import pipeline
from src.cli.db import db


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """PSC Hearing Intelligence CLI."""
    pass


cli.add_command(scraper)
cli.add_command(pipeline)
cli.add_command(db)


if __name__ == "__main__":
    cli()
