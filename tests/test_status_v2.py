"""Tests for status command v2 — always shows containers, rich output, hints."""

from unittest.mock import MagicMock, patch

import httpx
from click.testing import CliRunner

from dokployctl.cli import cli


def _mock_response(data, status_code=200):
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = data
    resp.is_error = status_code >= 400
    resp.status_code = status_code
    resp.text = str(data)
    return resp


@patch("dokployctl.status.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.status.make_client")
@patch("dokployctl.status.api_call")
@patch("dokployctl.status.get_containers")
def test_status_always_shows_containers(mock_containers, mock_api, mock_client, mock_config):
    mock_api.return_value = _mock_response(
        {
            "name": "test",
            "appName": "test-app",
            "composeStatus": "done",
            "sourceType": "raw",
            "composeType": "docker-compose",
            "composeFile": "x" * 100,
            "env": "KEY=val",
            "deployments": [{"title": "Deploy v1", "status": "done", "createdAt": "2026-03-24T19:30:00Z"}],
        }
    )
    mock_containers.return_value = [
        {"name": "test-app-web-1", "state": "running", "status": "Up 2h (healthy)", "containerId": "abc123", "image": "nginx:latest"},
    ]

    runner = CliRunner()
    result = runner.invoke(cli, ["status", "test-id"])
    assert result.exit_code == 0
    assert "Containers:" in result.output or "SERVICE" in result.output
    assert "[00:00]" in result.output
    assert "total)" in result.output


@patch("dokployctl.status.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.status.make_client")
@patch("dokployctl.status.api_call")
@patch("dokployctl.status.get_containers")
def test_status_hints_for_unhealthy(mock_containers, mock_api, mock_client, mock_config):
    mock_api.return_value = _mock_response(
        {
            "name": "test",
            "appName": "test-app",
            "composeStatus": "done",
            "sourceType": "raw",
            "composeType": "docker-compose",
            "composeFile": "x" * 100,
            "env": "",
            "deployments": [],
        }
    )
    mock_containers.return_value = [
        {"name": "test-app-worker-1", "state": "running", "status": "Up 2h (unhealthy)", "containerId": "abc123", "image": "img:tag"},
    ]

    runner = CliRunner()
    result = runner.invoke(cli, ["status", "test-id"])
    assert "Hint:" in result.output
    assert "worker" in result.output


@patch("dokployctl.status.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.status.make_client")
@patch("dokployctl.status.api_call")
@patch("dokployctl.status.get_containers")
def test_status_no_containers_shows_hint(mock_containers, mock_api, mock_client, mock_config):
    mock_api.return_value = _mock_response(
        {
            "name": "test",
            "appName": "test-app",
            "composeStatus": "stopped",
            "sourceType": "raw",
            "composeType": "docker-compose",
            "composeFile": "x" * 50,
            "env": "",
            "deployments": [],
        }
    )
    mock_containers.return_value = []

    runner = CliRunner()
    result = runner.invoke(cli, ["status", "test-id"])
    assert result.exit_code == 0
    assert "Hint:" in result.output


@patch("dokployctl.status.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.status.make_client")
@patch("dokployctl.status.api_call")
@patch("dokployctl.status.get_containers")
def test_status_summary_counts_containers(mock_containers, mock_api, mock_client, mock_config):
    mock_api.return_value = _mock_response(
        {
            "name": "aggre",
            "appName": "compose-aggre-abc",
            "composeStatus": "done",
            "sourceType": "raw",
            "composeType": "docker-compose",
            "composeFile": "x" * 2847,
            "env": "IMAGE_TAG=v1\nDB_PASSWORD=secret",
            "deployments": [{"title": "Deploy main-a1b2c3d", "status": "done", "createdAt": "2026-03-24T19:30:00Z"}],
        }
    )
    mock_containers.return_value = [
        {
            "name": "compose-aggre-abc-worker-1",
            "state": "running",
            "status": "Up 2h (healthy)",
            "containerId": "a1b2c3d4e5f6",
            "image": "ghcr.io/iorlas/aggre:main",
        },
        {
            "name": "compose-aggre-abc-db-1",
            "state": "running",
            "status": "Up 2h (healthy)",
            "containerId": "i9j0k1l2m3n4",
            "image": "postgres:16",
        },
    ]

    runner = CliRunner()
    result = runner.invoke(cli, ["status", "IWcYWttLzI"])
    assert result.exit_code == 0
    assert "2" in result.output
    assert "healthy" in result.output.lower()


@patch("dokployctl.status.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.status.make_client")
@patch("dokployctl.status.api_call")
@patch("dokployctl.status.get_containers")
def test_status_deprecated_live_flag_accepted(mock_containers, mock_api, mock_client, mock_config):
    """--live flag should be accepted (backward compat) but deprecated."""
    mock_api.return_value = _mock_response(
        {
            "name": "test",
            "appName": "test-app",
            "composeStatus": "done",
            "sourceType": "raw",
            "composeType": "docker-compose",
            "composeFile": "x" * 100,
            "env": "",
            "deployments": [],
        }
    )
    mock_containers.return_value = []

    runner = CliRunner()
    result = runner.invoke(cli, ["status", "test-id", "--live"])
    assert result.exit_code == 0
    assert "deprecated" in result.output.lower()
