"""Status command."""

import click

from dokployctl.client import DOKPLOY_ID, api_call, load_config, make_client, print_response
from dokployctl.containers import _container_ok, get_containers
from dokployctl.hints import hint_no_containers, hint_unhealthy
from dokployctl.output import format_container_table, parse_service_name
from dokployctl.timer import Timer


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("compose_id", type=DOKPLOY_ID)
@click.option("--live", "-l", is_flag=True, hidden=True, help="[deprecated] Containers are always shown now.")
def status(compose_id: str, live: bool) -> None:
    """Show compose app status."""
    timer = Timer()

    if live:
        click.echo("Warning: --live is deprecated; containers are always shown.")

    timer.log(f"Fetching compose app {compose_id}...")

    url, token = load_config()
    client = make_client(url, token)

    resp = api_call(client, "GET", "compose.one", {"composeId": compose_id})
    if resp.is_error:
        print_response(resp)
        return

    data = resp.json()
    app_name = data.get("appName", "?")
    click.echo(f"\nName:         {data.get('name', '?')}")
    click.echo(f"App name:     {app_name}")
    click.echo(f"Status:       {data.get('composeStatus', '?')}")
    compose_file = data.get("composeFile", "")
    click.echo(f"Compose:      {len(compose_file):,} chars")
    env = data.get("env", "")
    env_keys = [line.split("=")[0] for line in env.strip().splitlines() if "=" in line]
    click.echo(f"Env keys:     {', '.join(env_keys) if env_keys else '(none)'}")

    deployments = data.get("deployments", [])
    if deployments:
        latest = deployments[0]
        click.echo(f"\nLast deploy:  {latest.get('title', '?')} ({latest.get('status', '?')})")
        click.echo(f"  at:         {latest.get('createdAt', '?')}")
        if latest.get("errorMessage"):
            click.echo(f"  error:      {latest['errorMessage']}")

    containers = get_containers(client, app_name)

    click.echo("\nContainers:")
    if not containers:
        click.echo("  (none found)")
        click.echo("")
        click.echo(hint_no_containers(compose_id))
        timer.summary("No containers found.")
        return

    click.echo(format_container_table(containers, app_name))

    unhealthy = [c for c in containers if not _container_ok(c)]
    healthy_count = len(containers) - len(unhealthy)

    click.echo("")

    for c in unhealthy:
        service = parse_service_name(c.get("name", "?"), app_name)
        click.echo(hint_unhealthy(compose_id, service))

    if unhealthy:
        timer.summary(f"{healthy_count}/{len(containers)} containers healthy.")
    else:
        timer.summary(f"All {len(containers)} containers healthy.")
