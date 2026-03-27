"""Logs command."""

import click

from dokploy_ctl.client import DOKPLOY_ID, DashSafeCommand
from dokploy_ctl.dokploy import DokployClient
from dokploy_ctl.timer import Timer
from dokploy_ctl.websocket import fetch_container_logs, fetch_deploy_log


@click.command(cls=DashSafeCommand)
@click.argument("compose_id", type=DOKPLOY_ID)
@click.option("--service", "-s", default=None, help="Filter to a specific service name")
@click.option("--tail", "--lines", "-n", default=100, help="Number of lines (default: 100)")
@click.option("--since", default="5m", help="Time filter: 30s, 5m, 1h, all (default: 5m)")
@click.option("--deploy", "-D", "show_deploy", is_flag=True, help="Show deploy build log instead")
def logs(compose_id: str, service: str | None, tail: int, since: str, show_deploy: bool) -> None:
    """Show container runtime logs (or deploy build log with -D)."""
    timer = Timer()
    timer.log(f"Fetching logs for {compose_id} (last {since}, tail {tail})...")
    client = DokployClient()

    comp = client.get_compose(compose_id)
    app_name = comp.app_name

    if show_deploy:
        if not comp.deployments:
            click.echo("No deployments found.")
            return
        latest = comp.deployments[0]
        click.echo(f"Deploy: {latest.title} ({latest.status})")
        click.echo(f"  at:   {latest.created_at}")
        if not latest.log_path:
            click.echo("  (no log path)")
            return
        lines = fetch_deploy_log(client.url, client.token, latest.log_path, recv_timeout=5)
        if not lines:
            click.echo("  (no log content — file may have been cleaned up)")
            return
        for line in lines:
            click.echo(line.rstrip())
        return

    containers = client.get_containers(app_name)
    if not containers:
        click.echo("No running containers found.")
        return

    if service:
        containers = [c for c in containers if service in c.service]
        if not containers:
            click.echo(f"No container found matching service '{service}'")
            all_containers = client.get_containers(app_name)
            if all_containers:
                click.echo("Available services:")
                for c in all_containers:
                    click.echo(f"  {c.service}")
            return

    for c in containers:
        if not c.container_id:
            continue
        fetched = fetch_container_logs(client.url, client.token, c.container_id, tail=tail, since=since)
        if len(containers) > 1:
            click.echo(f"--- {c.service} (container: {c.container_id}) ---")
        for line in fetched:
            click.echo(line.rstrip())
        if len(containers) > 1:
            click.echo()
    timer.summary("Done.")
