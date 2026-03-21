"""Init command — create new compose app."""

import json
import sys

import click

from dokployctl.client import _err, api_call, load_config, make_client, print_response
from dokployctl.timer import Timer


@click.command()
@click.argument("project_id")
@click.argument("app_name")
def init(project_id: str, app_name: str) -> None:
    """Create new compose app (with sourceType fix)."""
    timer = Timer()
    url, token = load_config()
    client = make_client(url, token)

    timer.log("Creating compose app...")
    resp = api_call(
        client,
        "POST",
        "compose.create",
        {
            "name": app_name,
            "projectId": project_id,
        },
    )
    if resp.is_error:
        print_response(resp)
        return

    result = resp.json()
    compose_id = result.get("composeId")
    if not compose_id:
        _err("error: compose.create returned no composeId")
        click.echo(json.dumps(result, indent=2))
        sys.exit(1)

    timer.log(f"Created compose app: {compose_id}")

    timer.log("Fixing sourceType to 'raw'...")
    fix_resp = api_call(
        client,
        "POST",
        "compose.update",
        {
            "composeId": compose_id,
            "sourceType": "raw",
        },
    )
    if fix_resp.is_error:
        _err(f"warning: failed to fix sourceType (HTTP {fix_resp.status_code})")
    else:
        timer.log("Fixed sourceType to 'raw'")

    timer.summary(f"Done. Compose ID: {compose_id}")

    click.echo("\nNext steps:")
    click.echo(f"  dokployctl deploy {compose_id} docker-compose.prod.yml --env")
    click.echo(f"  dokployctl status {compose_id}")
