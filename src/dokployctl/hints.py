"""Deterministic hints — map error patterns to actionable suggestions."""


def hint_unhealthy(compose_id: str, service: str) -> str:
    return f"Hint: {service} is unhealthy.\n  dokployctl logs {compose_id} --service {service} --since 5m"


def hint_deploy_failed(compose_id: str, service: str, reason: str) -> str:
    return (
        f"Hint: {service} failed ({reason}). Check the Dockerfile entrypoint or config.\n"
        f"  dokployctl logs {compose_id} --service {service} --tail 200\n"
        f"  dokployctl status {compose_id}"
    )


def hint_restart(compose_id: str) -> str:
    return f"Hint: To restart: dokployctl start {compose_id}"


def hint_stopped(compose_id: str) -> str:
    return f"Hint: To start: dokployctl start {compose_id}"


def hint_no_containers(compose_id: str) -> str:
    return f"Hint: No containers found. The app may be stopped.\n  dokployctl start {compose_id}"
