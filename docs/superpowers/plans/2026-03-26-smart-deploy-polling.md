# Smart Deploy Polling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace dumb status polling with event-driven container transition tracking, and introduce a typed DokployClient to fix the find bug and simplify all commands.

**Architecture:** Task 1 creates `DokployClient` — a typed wrapper over the raw API. Task 2 creates the polling module with snapshot diffing, phase heuristics, and stall detection. Task 3 rewrites deploy to use both. Task 4 migrates remaining commands and fixes the find bug.

**Tech Stack:** Python 3.12+, click, httpx, websockets, pytest, dataclasses

**Spec:** `docs/superpowers/specs/2026-03-26-smart-deploy-polling.md`

---

## File Structure

```
src/dokploy_ctl/
├── dokploy.py          # NEW: DokployClient — typed API wrapper
├── polling.py          # NEW: PollSnapshot, transitions, phases, stalls
├── deploy.py           # MODIFY: use DokployClient + smart polling
├── find_cmd.py         # MODIFY: use DokployClient, fix environments nesting
├── status.py           # MODIFY: use DokployClient
├── logs.py             # MODIFY: use DokployClient
├── stop_cmd.py         # MODIFY: use DokployClient
├── start_cmd.py        # MODIFY: use DokployClient
├── restart_cmd.py      # MODIFY: use DokployClient
├── init_cmd.py         # MODIFY: use DokployClient
├── api_cmd.py          # KEEP: raw passthrough, still uses client.py
├── client.py           # KEEP: DokployID type + backward compat during migration
├── containers.py       # KEEP: _is_one_shot, _container_ok used by polling
├── ...                 # other files unchanged
tests/
├── test_dokploy.py     # NEW: DokployClient tests
├── test_polling.py     # NEW: transition, phase, stall tests
├── test_deploy_smart.py # NEW: smart polling integration test
├── test_find_fix.py    # NEW: find with correct nesting
```

---

### Task 1: DokployClient — typed API wrapper

**Files:**
- Create: `src/dokploy_ctl/dokploy.py`
- Create: `tests/test_dokploy.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_dokploy.py
from unittest.mock import MagicMock, patch
import httpx
from dokploy_ctl.dokploy import DokployClient, ComposeApp, ContainerInfo

def _mock_response(data, status_code=200):
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = data
    resp.is_error = status_code >= 400
    resp.status_code = status_code
    resp.text = str(data)
    return resp

def test_list_compose_apps_traverses_environments():
    """compose apps are under project.environments[].compose, not project.compose"""
    client = DokployClient.__new__(DokployClient)
    client._http = MagicMock()
    client._url = "https://example.com"
    client._token = "tok"

    client._http.get.return_value = _mock_response([
        {
            "name": "aggre",
            "projectId": "p1",
            "environments": [{
                "name": "production",
                "compose": [
                    {"composeId": "c1", "name": "aggre", "appName": "app-aggre", "composeStatus": "done"},
                    {"composeId": "c2", "name": "browserless", "appName": "app-bl", "composeStatus": "idle"},
                ]
            }]
        }
    ])
    apps = client.list_compose_apps()
    assert len(apps) == 2
    assert apps[0].compose_id == "c1"
    assert apps[0].project_name == "aggre"

def test_get_containers_filters_by_app_name():
    client = DokployClient.__new__(DokployClient)
    client._http = MagicMock()
    client._url = "https://example.com"
    client._token = "tok"

    client._http.get.return_value = _mock_response([
        {"containerId": "aaa", "name": "myapp-worker-1", "state": "running", "status": "Up 2h (healthy)", "image": "img:v1", "ports": ""},
        {"containerId": "bbb", "name": "other-db-1", "state": "running", "status": "Up 2h", "image": "pg:16", "ports": ""},
    ])
    containers = client.get_containers("myapp")
    assert len(containers) == 1
    assert containers[0].container_id == "aaa"
    assert containers[0].service == "worker"
    assert containers[0].health == "healthy"

def test_get_compose_returns_typed():
    client = DokployClient.__new__(DokployClient)
    client._http = MagicMock()
    client._url = "https://example.com"
    client._token = "tok"

    client._http.get.return_value = _mock_response({
        "composeId": "c1", "name": "aggre", "appName": "app-aggre",
        "composeStatus": "done", "composeFile": "version: '3'",
        "env": "KEY=val", "deployments": [{"deploymentId": "d1", "status": "done", "title": "Deploy v1", "createdAt": "2026-03-22", "logPath": "/tmp/log"}]
    })
    comp = client.get_compose("c1")
    assert comp.app_name == "app-aggre"
    assert comp.status == "done"
    assert len(comp.deployments) == 1
```

- [ ] **Step 2: Run tests, verify fail**

- [ ] **Step 3: Implement dokploy.py**

```python
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

    # ── Compose operations ──

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
                    if name_filter and name_filter.lower() not in proj_name.lower() and name_filter.lower() not in comp.get("name", "").lower():
                        continue
                    apps.append(ComposeApp(
                        compose_id=comp.get("composeId", ""),
                        name=comp.get("name", ""),
                        app_name=comp.get("appName", ""),
                        status=comp.get("composeStatus", ""),
                        project_name=proj_name,
                    ))
        return apps

    def update_compose(self, compose_id: str, compose_file: str, env: str | None = None) -> ComposeApp:
        payload: dict = {"composeId": compose_id, "composeFile": compose_file, "sourceType": "raw", "composePath": "./docker-compose.yml"}
        if env is not None:
            payload["env"] = env
        resp = self._post("compose.update", payload)
        if resp.is_error:
            click.echo(f"error: compose.update failed (HTTP {resp.status_code})", err=True)
            sys.exit(1)
        d = resp.json()
        return ComposeApp(compose_id=d.get("composeId", compose_id), name=d.get("name", ""), app_name=d.get("appName", ""), status=d.get("composeStatus", ""), compose_file=d.get("composeFile", ""), env=d.get("env", ""))

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
        return Deployment(deployment_id=d.get("deploymentId", ""), status=d.get("status", ""), title=d.get("title", ""), created_at=d.get("createdAt", ""), log_path=d.get("logPath", ""), error_message=d.get("errorMessage", ""))

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

    # ── Containers ──

    def get_containers(self, app_name: str) -> list[ContainerInfo]:
        resp = self._get("docker.getContainers")
        if resp.is_error:
            return []
        raw = resp.json()
        if not isinstance(raw, list):
            return []
        return [ContainerInfo.from_api(c, app_name) for c in raw if app_name in c.get("name", "")]
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Run lint:** `uv run ruff check src/dokploy_ctl/dokploy.py tests/test_dokploy.py`
- [ ] **Step 6: Commit**

```bash
git add src/dokploy_ctl/dokploy.py tests/test_dokploy.py
git commit -m "feat: DokployClient — typed API wrapper with correct environments nesting"
```

---

### Task 2: Polling module — transitions, phases, stalls

**Files:**
- Create: `src/dokploy_ctl/polling.py`
- Create: `tests/test_polling.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_polling.py
from dokploy_ctl.polling import PollSnapshot, detect_transitions, detect_phase, check_stall
from dokploy_ctl.dokploy import ContainerInfo

def _container(cid, service, state="running", health="healthy"):
    return ContainerInfo(container_id=cid, service=service, state=state, health=health, image="img", uptime="2h", raw_status=f"Up 2h ({health})")

def test_detect_transitions_disappeared():
    prev = [_container("aaa", "worker"), _container("bbb", "db")]
    curr = [_container("bbb", "db")]
    transitions = detect_transitions(prev, curr)
    assert any("worker" in t and "gone" in t for t in transitions)

def test_detect_transitions_appeared():
    prev = [_container("bbb", "db")]
    curr = [_container("bbb", "db"), _container("ccc", "worker", state="running", health="starting")]
    transitions = detect_transitions(prev, curr)
    assert any("worker" in t and "appeared" in t for t in transitions)

def test_detect_transitions_state_changed():
    prev = [_container("aaa", "worker", health="starting")]
    curr = [_container("aaa", "worker", health="healthy")]
    transitions = detect_transitions(prev, curr)
    assert any("worker" in t and "starting" in t and "healthy" in t for t in transitions)

def test_detect_transitions_no_change():
    prev = [_container("aaa", "worker")]
    curr = [_container("aaa", "worker")]
    transitions = detect_transitions(prev, curr)
    assert transitions == []

def test_detect_phase_shutdown():
    pre_deploy_ids = {"aaa", "bbb"}
    current = [_container("aaa", "worker")]  # bbb gone, no new
    phase = detect_phase(pre_deploy_ids, current)
    assert phase == "graceful shutdown"

def test_detect_phase_pulling():
    pre_deploy_ids = {"aaa", "bbb"}
    current = []  # all gone
    phase = detect_phase(pre_deploy_ids, current)
    assert phase == "image pull / startup"

def test_detect_phase_starting():
    pre_deploy_ids = {"aaa", "bbb"}
    current = [_container("ccc", "worker", health="starting"), _container("ddd", "db", health="healthy")]
    phase = detect_phase(pre_deploy_ids, current)
    assert phase == "containers starting"

def test_detect_phase_healthy():
    pre_deploy_ids = {"aaa", "bbb"}
    current = [_container("ccc", "worker"), _container("ddd", "db")]
    phase = detect_phase(pre_deploy_ids, current)
    assert phase == "healthy"

def test_detect_phase_rolling():
    pre_deploy_ids = {"aaa"}
    current = [_container("aaa", "worker-old"), _container("bbb", "worker-new", health="starting")]
    phase = detect_phase(pre_deploy_ids, current)
    assert phase == "rolling update"

def test_check_stall_no_stall():
    assert check_stall(last_transition_time=100.0, now=150.0, threshold=90) is False

def test_check_stall_stalled():
    assert check_stall(last_transition_time=100.0, now=200.0, threshold=90) is True
```

- [ ] **Step 2: Run tests, verify fail**

- [ ] **Step 3: Implement polling.py**

```python
"""Smart deploy polling — event-driven container transition tracking."""

from __future__ import annotations

from dataclasses import dataclass, field

from dokploy_ctl.dokploy import ContainerInfo


@dataclass
class PollSnapshot:
    containers: list[ContainerInfo]
    deploy_status: str
    transitions: list[str] = field(default_factory=list)
    phase: str = ""
    stalled: bool = False


def detect_transitions(prev: list[ContainerInfo], curr: list[ContainerInfo]) -> list[str]:
    """Compare two container lists and return human-readable transition strings."""
    prev_map = {c.container_id: c for c in prev}
    curr_map = {c.container_id: c for c in curr}
    transitions = []

    # Disappeared
    for cid, c in prev_map.items():
        if cid not in curr_map:
            transitions.append(f"{c.service}: {c.state} → gone")

    # Appeared
    for cid, c in curr_map.items():
        if cid not in prev_map:
            transitions.append(f"{c.service}: appeared ({c.health})")

    # State/health changed
    for cid in prev_map:
        if cid in curr_map:
            old = prev_map[cid]
            new = curr_map[cid]
            if old.state != new.state or old.health != new.health:
                old_label = old.health if old.health != "—" else old.state
                new_label = new.health if new.health != "—" else new.state
                transitions.append(f"{new.service}: {old_label} → {new_label}")

    return transitions


def detect_phase(pre_deploy_ids: set[str], current: list[ContainerInfo]) -> str:
    """Classify the deploy phase based on container ID sets."""
    current_ids = {c.container_id for c in current}
    old_remaining = pre_deploy_ids & current_ids
    new_ids = current_ids - pre_deploy_ids

    if not current:
        return "image pull / startup"
    if old_remaining and not new_ids:
        return "graceful shutdown"
    if old_remaining and new_ids:
        return "rolling update"
    if new_ids and not old_remaining:
        # All new — check if healthy
        all_ok = all(
            c.health == "healthy" or (c.state == "exited" and "Exited (0)" in c.raw_status)
            for c in current
        )
        if all_ok:
            return "healthy"
        return "containers starting"
    return "unknown"


def check_stall(last_transition_time: float, now: float, threshold: int = 90) -> bool:
    """Return True if no transitions for longer than threshold seconds."""
    return (now - last_transition_time) > threshold
```

- [ ] **Step 4: Run tests, verify pass**
- [ ] **Step 5: Commit**

```bash
git add src/dokploy_ctl/polling.py tests/test_polling.py
git commit -m "feat: polling module — transitions, phases, stall detection"
```

---

### Task 3: Deploy rewrite — smart polling with DokployClient

**Files:**
- Modify: `src/dokploy_ctl/deploy.py`
- Create: `tests/test_deploy_smart.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_deploy_smart.py
from unittest.mock import MagicMock, patch, PropertyMock
from click.testing import CliRunner
from dokploy_ctl.cli import cli

def test_deploy_shows_transitions_not_dumb_status(tmp_path):
    """Deploy should show container transitions, not 'status=running' repeated."""
    compose = tmp_path / "docker-compose.prod.yml"
    compose.write_text("version: '3'\nservices:\n  web:\n    image: nginx")

    with patch("dokploy_ctl.deploy.DokployClient") as MockClient:
        client = MockClient.return_value
        client.url = "https://example.com"
        client.token = "tok"

        # update_compose
        mock_compose = MagicMock()
        mock_compose.compose_file = "x" * 100
        mock_compose.env = ""
        client.update_compose.return_value = mock_compose

        # get_latest_deployment before deploy
        old_dep = MagicMock()
        old_dep.deployment_id = "old"
        client.get_latest_deployment.side_effect = [
            old_dep,  # snapshot
            MagicMock(deployment_id="new", status="done", error_message="", log_path=""),  # poll 1
        ]

        # trigger_deploy
        client.trigger_deploy.return_value = None

        # get_containers for snapshot + poll
        client.get_containers.side_effect = [
            [],  # pre-deploy snapshot (empty for simplicity)
            [MagicMock(container_id="c1", service="web", state="running", health="healthy", image="nginx", uptime="1m", raw_status="Up 1m (healthy)")],
        ]

        # get_compose for app_name
        client.get_compose.return_value = MagicMock(app_name="test-app")

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "test-id", str(compose)])

    assert "status=running" not in result.output  # no dumb polling
    assert "[00:00]" in result.output  # has timestamps
```

- [ ] **Step 2: Run tests, verify fail**

- [ ] **Step 3: Rewrite deploy.py**

Replace the deploy command's poll loop (lines 114-189) with smart polling:

1. Import `DokployClient` from `dokploy_ctl.dokploy`
2. Import `detect_transitions`, `detect_phase`, `check_stall` from `dokploy_ctl.polling`
3. Replace `load_config() + make_client()` with `DokployClient()`
4. Before `trigger_deploy`: snapshot containers via `client.get_containers(app_name)`, save IDs as `pre_deploy_ids`
5. Poll loop: each cycle calls both `client.get_latest_deployment()` and `client.get_containers(app_name)`
6. Compare containers with previous snapshot via `detect_transitions()`
7. Only emit output when transitions exist OR heartbeat interval (30s) reached
8. Emit phase label via `detect_phase(pre_deploy_ids, current_containers)`
9. Check stall via `check_stall()` — emit warning if stalled
10. On `phase == "healthy"` AND `deploy_status == "done"` → success
11. On `deploy_status == "error"` → emit transition history, then auto-fetch logs (existing behavior)
12. Remove Step 5 (verify_container_health) — absorbed into poll loop

Keep `_do_sync` and `sync` command unchanged (they don't poll). Update `deploy` only.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`

- [ ] **Step 5: Commit**

```bash
git add src/dokploy_ctl/deploy.py tests/test_deploy_smart.py
git commit -m "feat: smart deploy polling — transitions, phases, stall detection"
```

---

### Task 4: Migrate remaining commands to DokployClient + fix find

**Files:**
- Modify: `src/dokploy_ctl/find_cmd.py`
- Modify: `src/dokploy_ctl/status.py`
- Modify: `src/dokploy_ctl/logs.py`
- Modify: `src/dokploy_ctl/stop_cmd.py`
- Modify: `src/dokploy_ctl/start_cmd.py`
- Modify: `src/dokploy_ctl/restart_cmd.py`
- Modify: `src/dokploy_ctl/init_cmd.py`
- Create: `tests/test_find_fix.py`

- [ ] **Step 1: Write test for find fix**

```python
# tests/test_find_fix.py
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from dokploy_ctl.cli import cli

def test_find_returns_compose_apps_from_environments():
    """find must traverse environments[].compose, not project.compose"""
    with patch("dokploy_ctl.find_cmd.DokployClient") as MockClient:
        client = MockClient.return_value
        mock_app = MagicMock()
        mock_app.project_name = "aggre"
        mock_app.compose_id = "c1"
        mock_app.app_name = "app-aggre"
        mock_app.status = "done"
        client.list_compose_apps.return_value = [mock_app]

        runner = CliRunner()
        result = runner.invoke(cli, ["find"])

    assert "aggre" in result.output
    assert "c1" in result.output
```

- [ ] **Step 2: Run test, verify fail**

- [ ] **Step 3: Rewrite find_cmd.py to use DokployClient**

```python
"""Find command — list/search compose apps."""

import click

from dokploy_ctl.dokploy import DokployClient
from dokploy_ctl.timer import Timer


@click.command()
@click.argument("name", required=False)
def find(name: str | None) -> None:
    """List compose apps. Optionally filter by project name."""
    timer = Timer()
    client = DokployClient()

    timer.log("Searching projects...")
    apps = client.list_compose_apps(name_filter=name)

    if not apps:
        click.echo("No compose apps found." + (f" (filter: {name})" if name else ""))
        timer.summary("Done.")
        return

    click.echo(f"\n  {'PROJECT':<20} {'COMPOSE ID':<26} {'NAME':<20} {'STATUS'}")
    for app in apps:
        click.echo(f"  {app.project_name:<20} {app.compose_id:<26} {app.name:<20} {app.status}")

    timer.summary(f"\n{len(apps)} compose apps found.")
```

- [ ] **Step 4: Migrate remaining commands**

For each command (status, logs, stop, start, restart, init):
1. Replace `load_config() + make_client()` with `DokployClient()`
2. Replace `api_call(client, "GET", "compose.one", {...})` with `client.get_compose(id)`
3. Replace `get_containers(client, app_name)` with `client.get_containers(app_name)`
4. Replace `api_call(client, "POST", "compose.stop", {...})` with `client.stop_compose(id)`
5. Keep `api_cmd.py` unchanged (raw passthrough needs the old interface)

Each command becomes ~30% shorter. Example for `stop_cmd.py`:

```python
"""Stop command."""

import click

from dokploy_ctl.client import DOKPLOY_ID
from dokploy_ctl.dokploy import DokployClient
from dokploy_ctl.hints import hint_restart
from dokploy_ctl.timer import Timer


@click.command(context_settings={"ignore_unknown_options": True})
@click.argument("compose_id", type=DOKPLOY_ID)
def stop(compose_id: str) -> None:
    """Stop a running compose app."""
    timer = Timer()
    client = DokployClient()

    timer.log(f"Stopping compose {compose_id}...")
    client.stop_compose(compose_id)

    click.echo(hint_restart(compose_id))
    timer.summary("Stopped.")
```

- [ ] **Step 5: Run full test suite**

Run: `make check`

- [ ] **Step 6: Commit**

```bash
git add src/dokploy_ctl/ tests/test_find_fix.py
git commit -m "feat: migrate all commands to DokployClient, fix find environments nesting"
```

---

### Task 5: Version bump + push

**Files:**
- Modify: `src/dokploy_ctl/__init__.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Bump version to 0.3.0**

- [ ] **Step 2: Run full check**

Run: `make check`

- [ ] **Step 3: Commit and push**

```bash
git add src/dokploy_ctl/__init__.py pyproject.toml uv.lock
git commit -m "feat: v0.3.0 — smart deploy polling, DokployClient, find fix"
git push
```

- [ ] **Step 4: Reinstall locally**

```bash
uv tool install --force .
dokploy-ctl --version  # should show 0.3.0
dokploy-ctl find       # should now list all compose apps correctly
```
