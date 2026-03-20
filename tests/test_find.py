# tests/test_find.py
from unittest.mock import MagicMock, patch

import httpx
from click.testing import CliRunner

from dokployctl.cli import cli


def _mock_response(data, status_code=200):
    resp = MagicMock(spec=httpx.Response)
    resp.json.return_value = data
    resp.is_error = status_code >= 400
    resp.status_code = status_code
    return resp


@patch("dokployctl.find_cmd.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.find_cmd.make_client")
@patch("dokployctl.find_cmd.api_call")
def test_find_lists_all(mock_api, mock_client, mock_config):
    mock_api.return_value = _mock_response(
        [
            {"name": "aggre", "compose": [{"composeId": "abc", "appName": "app-1", "composeStatus": "done"}]},
            {"name": "reelm", "compose": [{"composeId": "def", "appName": "app-2", "composeStatus": "done"}]},
        ]
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["find"])
    assert result.exit_code == 0
    assert "aggre" in result.output
    assert "reelm" in result.output
    assert "abc" in result.output


@patch("dokployctl.find_cmd.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.find_cmd.make_client")
@patch("dokployctl.find_cmd.api_call")
def test_find_filters_by_name(mock_api, mock_client, mock_config):
    mock_api.return_value = _mock_response(
        [
            {"name": "aggre", "compose": [{"composeId": "abc", "appName": "app-1", "composeStatus": "done"}]},
            {"name": "reelm", "compose": [{"composeId": "def", "appName": "app-2", "composeStatus": "done"}]},
        ]
    )
    runner = CliRunner()
    result = runner.invoke(cli, ["find", "aggre"])
    assert "aggre" in result.output
    assert "reelm" not in result.output


@patch("dokployctl.find_cmd.load_config", return_value=("https://example.com", "token"))
@patch("dokployctl.find_cmd.make_client")
@patch("dokployctl.find_cmd.api_call")
def test_find_no_results(mock_api, mock_client, mock_config):
    mock_api.return_value = _mock_response([])
    runner = CliRunner()
    result = runner.invoke(cli, ["find"])
    assert "No compose apps found" in result.output
