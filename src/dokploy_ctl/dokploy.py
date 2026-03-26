"""Typed Dokploy API client."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import click
import httpx

from dokploy_ctl.output import parse_health, parse_service_name, parse_uptime

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "dokploy"
TIMEOUT = 30.0


@dataclass
class ContainerInfo:
    container_id: str
    service: str
    state: str
    health: str
    image: str
    uptime: str
    raw_status: str

    @classmethod
    def from_api(cls, data: dict, app_name: str) -> ContainerInfo:
        return cls(
            container_id=data.get("containerId", ""),
            service=parse_service_name(data.get("name", ""), app_name),
            state=data.get("state", ""),
            health=parse_health(data.get("status", "")),
            image=data.get("image", ""),
            uptime=parse_uptime(data.get("status", "")),
            raw_status=data.get("status", ""),
        )


@dataclass
class Deployment:
    deployment_id: str
    status: str
    title: str
    created_at: str
    log_path: str
    error_message: str = ""


@dataclass
class ComposeApp:
    compose_id: str
    name: str
    app_name: str
    status: str
    project_name: str = ""
    compose_file: str = ""
    env: str = ""
    deployments: list[Deployment] = field(default_factory=list)


class DokployClient:
    """Typed wrapper over the Dokploy tRPC API."""

    def __init__(self, config_dir: Path = DEFAULT_CONFIG_DIR) -> None:
        token_path = config_dir / "token"
        url_path = config_dir / "url"

        errors = []
        if not token_path.exists():
            errors.append(f"Missing token file: {token_path}")
        if not url_path.exists():
            errors.append(f"Missing URL file: {url_path}")
        if errors:
            for e in errors:
                click.echo(f"error: {e}", err=True)
            click.echo(
                f"\nSetup:\n  dokploy-ctl login --url <url> --token <token>\n"
                f"  Or manually:\n  mkdir -p {config_dir}\n"
                f"  echo 'YOUR_TOKEN' > {token_path}\n"
                f"  echo 'https://your-dokploy-url' > {url_path}",
                err=True,
            )
            sys.exit(1)

        self._token = token_path.read_text().strip()
        self._url = url_path.read_text().strip().rstrip("/")

        if not self._url or not self._url.startswith(("http://", "https://")):
            click.echo(f"error: invalid URL in {url_path}: '{self._url}'", err=True)
            click.echo("Fix: dokploy-ctl login --url https://your-dokploy-url --token <token>", err=True)
            sys.exit(1)

        verify = os.environ.get("DOKPLOY_INSECURE", "").lower() not in ("1", "true", "yes")
        self._http = httpx.Client(
            base_url=self._url,
            headers={"x-api-key": self._token, "Content-Type": "application/json"},
            timeout=TIMEOUT,
            verify=verify,
        )

    @property
    def url(self) -> str:
        return self._url

    @property
    def token(self) -> str:
        return self._token

    def _get(self, endpoint: str, params: dict | None = None) -> httpx.Response:
        return self._http.get(f"/api/{endpoint}", params=params)

    def _post(self, endpoint: str, data: dict | None = None) -> httpx.Response:
        return self._http.post(f"/api/{endpoint}", json=data)

    # -- Compose operations --

    def get_compose(self, compose_id: str) -> ComposeApp:
        resp = self._get("compose.one", {"composeId": compose_id})
        if resp.is_error:
            click.echo(f"error: compose.one failed (HTTP {resp.status_code})", err=True)
            sys.exit(1)
        d = resp.json()
        return ComposeApp(
            compose_id=d.get("composeId", ""),
            name=d.get("name", ""),
            app_name=d.get("appName", ""),
            status=d.get("composeStatus", ""),
            compose_file=d.get("composeFile", ""),
            env=d.get("env", ""),
            deployments=[
                Deployment(
                    deployment_id=dep.get("deploymentId", ""),
                    status=dep.get("status", ""),
                    title=dep.get("title", ""),
                    created_at=dep.get("createdAt", ""),
                    log_path=dep.get("logPath", ""),
                    error_message=dep.get("errorMessage", ""),
                )
                for dep in d.get("deployments", [])
            ],
        )

    def list_compose_apps(self, name_filter: str | None = None) -> list[ComposeApp]:
        resp = self._get("project.all")
        if resp.is_error:
            click.echo(f"error: project.all failed (HTTP {resp.status_code})", err=True)
            sys.exit(1)
        apps = []
        for proj in resp.json():
            proj_name = proj.get("name", "?")
            for env in proj.get("environments", []):
                for comp in env.get("compose", []):
                    comp_name = comp.get("name", "").lower()
                    if name_filter and name_filter.lower() not in proj_name.lower() and name_filter.lower() not in comp_name:
                        continue
                    apps.append(
                        ComposeApp(
                            compose_id=comp.get("composeId", ""),
                            name=comp.get("name", ""),
                            app_name=comp.get("appName", ""),
                            status=comp.get("composeStatus", ""),
                            project_name=proj_name,
                        )
                    )
        return apps

    def update_compose(self, compose_id: str, compose_file: str, env: str | None = None) -> ComposeApp:
        payload: dict = {
            "composeId": compose_id,
            "composeFile": compose_file,
            "sourceType": "raw",
            "composePath": "./docker-compose.yml",
        }
        if env is not None:
            payload["env"] = env
        resp = self._post("compose.update", payload)
        if resp.is_error:
            click.echo(f"error: compose.update failed (HTTP {resp.status_code})", err=True)
            sys.exit(1)
        d = resp.json()
        return ComposeApp(
            compose_id=d.get("composeId", compose_id),
            name=d.get("name", ""),
            app_name=d.get("appName", ""),
            status=d.get("composeStatus", ""),
            compose_file=d.get("composeFile", ""),
            env=d.get("env", ""),
        )

    def trigger_deploy(self, compose_id: str, title: str = "") -> None:
        resp = self._post("compose.deploy", {"composeId": compose_id, "title": title})
        if resp.is_error:
            click.echo(f"error: compose.deploy failed (HTTP {resp.status_code})", err=True)
            sys.exit(1)

    def get_latest_deployment(self, compose_id: str) -> Deployment | None:
        resp = self._get("deployment.allByCompose", {"composeId": compose_id})
        if resp.is_error:
            return None
        deps = resp.json()
        if not deps or not isinstance(deps, list):
            return None
        d = deps[0]
        return Deployment(
            deployment_id=d.get("deploymentId", ""),
            status=d.get("status", ""),
            title=d.get("title", ""),
            created_at=d.get("createdAt", ""),
            log_path=d.get("logPath", ""),
            error_message=d.get("errorMessage", ""),
        )

    def stop_compose(self, compose_id: str) -> None:
        resp = self._post("compose.stop", {"composeId": compose_id})
        if resp.is_error:
            click.echo(f"error: compose.stop failed (HTTP {resp.status_code})", err=True)
            sys.exit(1)

    def start_compose(self, compose_id: str) -> None:
        resp = self._post("compose.start", {"composeId": compose_id})
        if resp.is_error:
            click.echo(f"error: compose.start failed (HTTP {resp.status_code})", err=True)
            sys.exit(1)

    def redeploy_compose(self, compose_id: str) -> None:
        resp = self._post("compose.redeploy", {"composeId": compose_id})
        if resp.is_error:
            click.echo(f"error: compose.redeploy failed (HTTP {resp.status_code})", err=True)
            sys.exit(1)

    def restart_container(self, container_id: str) -> None:
        resp = self._post("docker.restartContainer", {"containerId": container_id})
        if resp.is_error:
            click.echo(f"error: docker.restartContainer failed (HTTP {resp.status_code})", err=True)
            sys.exit(1)

    # -- Containers --

    def get_containers(self, app_name: str) -> list[ContainerInfo]:
        resp = self._get("docker.getContainers")
        if resp.is_error:
            return []
        raw = resp.json()
        if not isinstance(raw, list):
            return []
        return [ContainerInfo.from_api(c, app_name) for c in raw if app_name in c.get("name", "")]
