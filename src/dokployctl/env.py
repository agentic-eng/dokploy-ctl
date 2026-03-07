import os
import re
import sys
from pathlib import Path

import click


def extract_env_vars(compose_content: str) -> list[str]:
    """Find all ${VAR} references in a compose file."""
    return sorted(set(re.findall(r"\$\{(\w+)\}", compose_content)))


def build_env_from_compose(compose_content: str) -> str:
    """Read ${VAR} refs from compose, resolve from os.environ, validate."""
    var_names = extract_env_vars(compose_content)
    if not var_names:
        return ""

    missing = [v for v in var_names if not os.environ.get(v)]
    if missing:
        click.echo("error: Missing environment variables referenced in compose file:", err=True)
        for v in missing:
            click.echo(f"  ${{{v}}}", err=True)
        click.echo("\nSet them in the environment before running dokployctl.", err=True)
        sys.exit(1)

    lines = [f"{v}={os.environ[v]}" for v in var_names]
    click.echo(f"Env: {len(var_names)} vars resolved from compose: {', '.join(var_names)}")
    return "\n".join(lines)


def resolve_env(env_file: str | None, compose_content: str) -> str | None:
    """Resolve env from --env-file or auto-detect from compose ${VAR} refs."""
    if env_file:
        return Path(env_file).read_text()
    env_vars = extract_env_vars(compose_content)
    if env_vars:
        return build_env_from_compose(compose_content)
    return None
