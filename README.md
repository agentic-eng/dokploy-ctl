# dokployctl

AI-native CLI for Dokploy deployments — deploy, sync, inspect, debug from the terminal (and from agents).

## Install

```bash
pip install dokployctl
# or
uv tool install dokployctl
```

## Quick Start

```bash
dokployctl login --url https://your-dokploy.example.com --token <api-token>
dokployctl deploy <compose-app-id> docker-compose.prod.yml
```

## Commands

| Command  | Description                                                        |
|----------|--------------------------------------------------------------------|
| `login`  | Store Dokploy credentials                                          |
| `deploy` | Sync + deploy + poll + verify container health (LDD output)        |
| `sync`   | Sync compose file + env to Dokploy (without deploying)             |
| `status` | Show compose app status with live containers                       |
| `logs`   | Show container runtime logs (`-D` for deploy log)                  |
| `api`    | Raw API call (like `gh api`)                                       |
| `init`   | Create new compose app                                             |
| `find`   | Search compose apps by name                                        |
| `stop`   | Stop a compose app                                                 |
| `start`  | Start a compose app                                                |

Bare `dokployctl` lists all compose apps.

## LDD Output

`deploy` emits timestamped, machine-readable lines for agent pipelines:

```
[2026-03-25T14:02:01Z] deploy started  app=my-app
[2026-03-25T14:02:03Z] sync done
[2026-03-25T14:02:04Z] deploy triggered
[2026-03-25T14:02:31Z] deploy done  elapsed=27s
[2026-03-25T14:02:33Z] health ok  containers=3/3
```

## Upgrading from v0.1

Breaking changes in v0.2:

- **`deploy` no longer auto-resolves env vars** — pass `--env KEY=VAL` or `--env-file .env` explicitly in CI
- **`logs --since` default changed** from `all` to `5m` — add `--since all` to restore previous behavior
- **`status` always shows live containers** — `--live` flag removed, it's now the default
- **Bare `dokployctl`** lists compose apps instead of showing help

## Links

- [Dokploy](https://dokploy.com)

## License

MIT
