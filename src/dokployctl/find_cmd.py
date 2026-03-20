"""Find command — list/search compose apps."""

import click

from dokployctl.client import _err, api_call, load_config, make_client
from dokployctl.timer import Timer


@click.command()
@click.argument("name", required=False)
def find(name: str | None) -> None:
    """List compose apps. Optionally filter by project name."""
    timer = Timer()
    url, token = load_config()
    client = make_client(url, token)

    timer.log("Searching projects...")
    resp = api_call(client, "GET", "project.all")
    if resp.is_error:
        _err(f"error: failed to list projects (HTTP {resp.status_code})")
        raise SystemExit(1)

    projects = resp.json()
    rows = []
    for proj in projects:
        proj_name = proj.get("name", "?")
        for comp in proj.get("compose", []):
            comp_id = comp.get("composeId", "?")
            app_name = comp.get("appName", "?")
            status = comp.get("composeStatus", "?")
            if name and name.lower() not in proj_name.lower() and name.lower() not in app_name.lower():
                continue
            rows.append((proj_name, comp_id, app_name, status))

    if not rows:
        click.echo("No compose apps found." + (f" (filter: {name})" if name else ""))
        timer.summary("Done.")
        return

    click.echo(f"\n  {'PROJECT':<20} {'COMPOSE ID':<26} {'APP NAME':<46} {'STATUS'}")
    for proj_name, comp_id, app_name, status in rows:
        click.echo(f"  {proj_name:<20} {comp_id:<26} {app_name:<46} {status}")

    timer.summary(f"\n{len(rows)} compose apps found.")
