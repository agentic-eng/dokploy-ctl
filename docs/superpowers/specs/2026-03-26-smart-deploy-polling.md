# Smart Deploy Polling — Event-Driven Container Tracking

## Goal

Replace dumb `status=running` polling with event-driven container transition tracking. The deploy command becomes an event stream that emits transitions, phase labels, and stall warnings — giving AI agents (and humans) full situational awareness during deployments.

## Motivation

Real deployment trace from aggre (9,423 char compose, 12 env vars, 5 services):
- 60 identical `Polling... status=running` lines over 5 minutes
- Timed out at 300s even though deploy was actually progressing
- Zero visibility into what was happening: shutdown? image pull? health convergence?
- Agent had no signal to distinguish "normal slow deploy" from "stuck deploy"

## Design

### Data Model: PollSnapshot

Each poll cycle produces a snapshot:

```python
@dataclass
class ContainerState:
    container_id: str
    service: str        # parsed from container name
    state: str          # running, exited, restarting, created
    health: str         # healthy, unhealthy, starting, —
    image: str

@dataclass
class PollSnapshot:
    timestamp: float
    deploy_status: str                    # from Dokploy API
    containers: dict[str, ContainerState] # keyed by container_id
    transitions: list[str]                # human-readable transition lines
    phase: str                            # heuristic phase label
    stalled: bool                         # no transitions for stall_threshold
```

### Transition Detection

Compare container lists between consecutive snapshots by container ID:

| Change | Event |
|---|---|
| ID in previous, not in current | `worker: running → gone` |
| ID in current, not in previous | `worker: appeared (starting)` |
| Same ID, different state/health | `worker: starting → healthy` |
| Same ID, same state | (suppressed — no output) |

Container IDs are the truth — service names are derived from container names using `parse_service_name()` from `output.py`.

### Phase Heuristics

Derived from comparing current containers against the pre-deploy snapshot:

| Condition | Phase label |
|---|---|
| Old container IDs still present, no new ones | `graceful shutdown` |
| No containers at all (old gone, new not yet) | `image pull / startup` |
| New container IDs appearing, some not healthy | `containers starting` |
| All containers present and healthy | `healthy` |
| Mix of old and new container IDs coexisting | `rolling update` |

**Old vs new**: determined by comparing current container IDs against the set captured before `compose.deploy` was triggered.

Phase labels are heuristic — they may be wrong. The raw transitions are always emitted alongside them so the agent can override the heuristic's judgment.

### Stall Detection

If no transitions detected for `stall_threshold` seconds (default: 90):

```
[03:00] WARNING: no container changes for 90s. Deploy may be stalled.
[03:00]   Last change: worker stopped at [01:30]. No new containers since.
[03:00]   Hint: dokploy-ctl logs <id> -D    (check deploy build log)
```

Stall warnings are advisory — the tool does not abort. The agent decides whether to wait or investigate.

### Output Format

**Key change: only print when something changes.** No more `Polling... status=running` every 6 seconds.

Periodic heartbeat every 30s if no transitions (so the agent knows the tool isn't hung):

```
[00:00] Triggering deploy (Deploy main-10eea69)...
[00:00] Snapshot: 5 containers (worker, db, hatchet-lite, garage, browserless)
[00:07] deploy=running | Phase: graceful shutdown
[00:25] worker: running → stopped
[00:31] db: running → stopped
[00:37] All old containers stopped. Phase: image pull / startup
[01:07] (no changes for 30s — still in image pull / startup)
[01:15] db: appeared (starting)
[01:21] worker: appeared (starting) | db: starting → healthy
[01:37] (no changes for 30s — waiting for health convergence)
[02:00] worker: starting → healthy
[02:00] Phase: healthy. All 5 containers up.
[02:06] Dokploy reports deploy done.
[02:06] All containers healthy. Deploy succeeded. (126s total)
```

Stalled deploy:
```
[00:00] Triggering deploy (Deploy main-10eea69)...
[00:00] Snapshot: 5 containers (worker, db, hatchet-lite, garage, browserless)
[00:07] deploy=running | Phase: graceful shutdown
[00:25] worker: running → stopped
[01:55] WARNING: no container changes for 90s. Deploy may be stalled.
[01:55]   Last change: worker → stopped at [00:25]
[01:55]   Hint: dokploy-ctl logs <id> -D    (check deploy build log)
[02:25] (no changes for 30s — still stalled)
```

### API Calls Per Cycle

Each poll cycle makes 2 API calls (was 1):
1. `deployment.allByCompose` — deploy status (existing)
2. `docker.getContainers` — container states (new)

The second call is lightweight (GET, returns JSON array). At 6s intervals over a 5-minute deploy, that's ~50 extra API calls total.

### Implementation Scope

**Files to modify:**
- `src/dokploy_ctl/deploy.py` — replace the poll loop with smart polling

**Files to create:**
- `src/dokploy_ctl/polling.py` — `PollSnapshot`, transition detection, phase heuristics, stall detection
- `tests/test_polling.py` — unit tests for transition detection and phase classification

**Files unchanged:**
- All other commands — only `deploy` uses this
- `containers.py` — reuse `get_containers()` as-is

### Configuration

| Setting | Default | Flag |
|---|---|---|
| Poll interval | 6s | (not configurable — fast enough for transitions) |
| Stall threshold | 90s | `--stall-threshold` (or env `DOKPLOY_STALL_THRESHOLD`) |
| Heartbeat interval | 30s | (not configurable) |
| Deploy timeout | 600s | `--timeout` (existing) |

### Exit Codes

No change — exit 0 on success, exit 1 on failure/timeout. The stall warning does NOT change the exit code.
