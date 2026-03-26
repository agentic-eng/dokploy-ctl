# tests/test_dokploy.py
from unittest.mock import MagicMock

import httpx

from dokploy_ctl.dokploy import DokployClient


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

    client._http.get.return_value = _mock_response(
        [
            {
                "name": "aggre",
                "projectId": "p1",
                "environments": [
                    {
                        "name": "production",
                        "compose": [
                            {"composeId": "c1", "name": "aggre", "appName": "app-aggre", "composeStatus": "done"},
                            {"composeId": "c2", "name": "browserless", "appName": "app-bl", "composeStatus": "idle"},
                        ],
                    }
                ],
            }
        ]
    )
    apps = client.list_compose_apps()
    assert len(apps) == 2
    assert apps[0].compose_id == "c1"
    assert apps[0].project_name == "aggre"


def test_get_containers_filters_by_app_name():
    client = DokployClient.__new__(DokployClient)
    client._http = MagicMock()
    client._url = "https://example.com"
    client._token = "tok"

    client._http.get.return_value = _mock_response(
        [
            {
                "containerId": "aaa",
                "name": "myapp-worker-1",
                "state": "running",
                "status": "Up 2h (healthy)",
                "image": "img:v1",
                "ports": "",
            },
            {"containerId": "bbb", "name": "other-db-1", "state": "running", "status": "Up 2h", "image": "pg:16", "ports": ""},
        ]
    )
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

    client._http.get.return_value = _mock_response(
        {
            "composeId": "c1",
            "name": "aggre",
            "appName": "app-aggre",
            "composeStatus": "done",
            "composeFile": "version: '3'",
            "env": "KEY=val",
            "deployments": [
                {
                    "deploymentId": "d1",
                    "status": "done",
                    "title": "Deploy v1",
                    "createdAt": "2026-03-22",
                    "logPath": "/var/log/deploy.log",
                }
            ],
        }
    )
    comp = client.get_compose("c1")
    assert comp.app_name == "app-aggre"
    assert comp.status == "done"
    assert len(comp.deployments) == 1
