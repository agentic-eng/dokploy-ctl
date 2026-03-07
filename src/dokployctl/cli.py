"""CLI entry point — click group + login command."""

import click

from dokployctl.client import DEFAULT_CONFIG_DIR


@click.group()
@click.version_option(package_name="dokployctl")
def cli() -> None:
    """dokployctl — CLI for Dokploy deployments."""


@cli.command()
@click.option("--url", required=True, help="Dokploy instance URL")
@click.option("--token", required=True, help="API token")
def login(url: str, token: str) -> None:
    """Store Dokploy credentials."""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (DEFAULT_CONFIG_DIR / "url").write_text(url.rstrip("/") + "\n")
    (DEFAULT_CONFIG_DIR / "token").write_text(token + "\n")
    click.echo(f"Saved credentials to {DEFAULT_CONFIG_DIR}")
