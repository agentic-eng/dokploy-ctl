"""Raw API call command."""

import json

import click

from dokploy_ctl.client import api_call, load_config, make_client, print_response

# Known Dokploy tRPC endpoints used by dokploy-ctl
KNOWN_ENDPOINTS = [
    ("compose.one", "GET", "Get compose app details (requires composeId)"),
    ("compose.create", "POST", "Create a new compose app"),
    ("compose.update", "POST", "Update compose file and env"),
    ("compose.deploy", "POST", "Trigger a deploy (requires composeId, title)"),
    ("compose.stop", "POST", "Stop a compose app"),
    ("compose.start", "POST", "Start a stopped compose app"),
    ("compose.redeploy", "POST", "Redeploy (restart) a compose app"),
    ("deployment.allByCompose", "GET", "List deployments for a compose app"),
    ("docker.getContainers", "GET", "List all Docker containers"),
    ("docker.restartContainer", "POST", "Restart a specific container"),
    ("project.all", "GET", "List all projects and their apps"),
]


@click.command()
@click.argument("endpoint", required=False)
@click.option("--data", "-d", default=None, help="JSON body (POST) or query params (GET with -X GET)")
@click.option("--method", "-X", default=None, help="HTTP method (default: POST if --data, GET otherwise)")
@click.option("--list", "list_endpoints", is_flag=True, help="List known API endpoints")
def api(endpoint: str | None, data: str | None, method: str | None, list_endpoints: bool) -> None:
    """Raw API call (like gh api). Use --list to discover endpoints."""
    if list_endpoints:
        click.echo("Known Dokploy API endpoints:")
        click.echo(f"  {'ENDPOINT':<30} {'METHOD':<8} DESCRIPTION")
        for name, m, desc in KNOWN_ENDPOINTS:
            click.echo(f"  {name:<30} {m:<8} {desc}")
        click.echo('\nUsage: dokploy-ctl api <endpoint> [-d \'{"key": "val"}\'] [-X GET|POST]')
        return

    if not endpoint:
        click.echo("Error: Missing argument 'ENDPOINT'. Use --list to see available endpoints.", err=True)
        raise SystemExit(1)

    url, token = load_config()
    client = make_client(url, token)
    parsed = json.loads(data) if data else None
    m = (method or ("POST" if parsed else "GET")).upper()
    resp = api_call(client, m, endpoint, parsed)
    print_response(resp)
