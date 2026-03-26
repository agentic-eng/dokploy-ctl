"""Smart deploy polling — event-driven container transition tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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
    for cid, old in prev_map.items():
        if cid in curr_map:
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
        all_ok = all(c.health == "healthy" or (c.state == "exited" and "Exited (0)" in c.raw_status) for c in current)
        if all_ok:
            return "healthy"
        return "containers starting"
    return "unknown"


def check_stall(last_transition_time: float, now: float, threshold: int = 90) -> bool:
    """Return True if no transitions for longer than threshold seconds."""
    return (now - last_transition_time) > threshold
