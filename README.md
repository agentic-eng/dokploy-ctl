# dokploy-ctl

**AI-native CLI for [Dokploy](https://dokploy.com) deployments.**

Deploy, sync, inspect, and debug your Dokploy compose apps from the terminal — designed for AI agents and humans alike. Every command is a workflow: it narrates what it's doing, auto-escalates on failure, and tells you what to do next.

## Install

```bash
pip install git+https://github.com/agentic-eng/dokploy-ctl.git

# or
uv tool install git+https://github.com/agentic-eng/dokploy-ctl.git
```

## Quick Start

```bash
# 1. Authenticate
dokploy-ctl login --url https://your-dokploy.example.com --token <api-token>

# 2. See what's running
dokploy-ctl find

# 3. Deploy
dokploy-ctl deploy <compose-id> docker-compose.prod.yml
```

## Commands

| Command | What it does |
|---------|-------------|
| `find [name]` | List all compose apps, optionally filter by name |
| `status <id>` | Full picture: compose config + live containers + health hints |
| `deploy <id> <file>` | Sync compose, trigger deploy, poll, health-check, auto-diagnose on failure |
| `sync <id> <file>` | Push compose file to Dokploy without deploying |
| `stop <id>` | Stop a compose app |
| `start <id>` | Start a compose app + verify health |
| `logs <id>` | Container logs (default: last 5m). `-D` for deploy build log |
| `init <project-id> <name>` | Create new compose app with sourceType fix |
| `api <endpoint>` | Raw API passthrough (escape hatch) |
| `login` | Store credentials |

Running `dokploy-ctl` with no arguments lists all compose apps.

## How It Works

Every command emits **timestamped, narrated output** — designed for AI agents to parse and act on:

```
[00:00] Syncing compose file (2,847 chars)...
[00:01] Synced. 2,847 chars persisted, sourceType=raw.
[00:01] Triggering deploy (Deploy main-a1b2c3d)...
[00:06] Polling... [1/60] status=running
[00:11] Polling... [2/60] status=done
[00:11] Verifying container health...
[00:16]   worker=ok, db=ok, migrate=exited(0)
[00:16] All containers healthy. Deploy succeeded. (16s total)
```

On failure, `deploy` **auto-fetches logs** and **suggests the next command**:

```
[00:11] Deploy failed: "exit code 1"
[00:12] === Logs: worker (exited, container: a1b2c3d4) ===
[00:12]   FileNotFoundError: /app/run.sh
[00:12]
[00:12] Hint: worker failed (exited(1)). Check the Dockerfile entrypoint.
[00:12]   dokploy-ctl logs IWcYWttLzI --service worker --tail 200
```

## CI Usage

```yaml
- name: Deploy
  env:
    DOKPLOY_AUTH_TOKEN: ${{ secrets.DOKPLOY_AUTH_TOKEN }}
    DOKPLOY_URL: ${{ secrets.DOKPLOY_URL }}
    IMAGE_TAG: main-${{ github.sha }}
    # all secrets referenced in docker-compose.prod.yml:
    # DB_PASSWORD: ${{ secrets.DB_PASSWORD }}
  run: |
    pip install git+https://github.com/agentic-eng/dokploy-ctl.git
    dokploy-ctl login --url "$DOKPLOY_URL" --token "$DOKPLOY_AUTH_TOKEN"
    dokploy-ctl deploy "$DOKPLOY_COMPOSE_ID" docker-compose.prod.yml --env
```

Use `--env` in CI to resolve `${VAR}` references from the environment. Without it, Dokploy uses its stored env.

## Design Principles

**Every command is a workflow, not an operation.** Deploy doesn't just trigger — it syncs, polls, health-checks, and diagnoses failures automatically.

**Hints, not silence.** When something is wrong, the output says what and suggests the exact next command.

**Zero-guessing discovery.** Bare `dokploy-ctl` lists your apps. Errors include the fix command. Service names and container IDs appear in every reference.

**Built for AI agents.** Timestamped output, deterministic hints, structured narratives. Designed so agents never need to fall back to raw API calls or SSH.

## License

MIT
