from pathlib import Path
import socket
import yaml
import tomllib
from analytics_agent.engine import Engine
from analytics_agent.models import AnalyticsRequest

ROOT = Path(__file__).resolve().parents[1]


def test_render_configuration_uses_assigned_port_and_bundled_data():
    service = yaml.safe_load((ROOT / "render.yaml").read_text())["services"][0]
    assert service["type"] == "web"
    assert service["plan"] == "free"
    assert "--server.address 0.0.0.0" in service["startCommand"]
    assert "--server.port $PORT" in service["startCommand"]
    assert service["healthCheckPath"] == "/_stcore/health"
    assert "disk" not in service and service["autoDeploy"] is False
    assert service["region"] == "singapore"
    assert {item["key"]:item.get("value") for item in service["envVars"]}["OLLAMA_BASE_URL"] == ""
    assert {item["key"]:item.get("value") for item in service["envVars"]}["DUCKDB_MEMORY_LIMIT"] == "320MB"
    assert {item["key"]:item.get("value") for item in service["envVars"]}["RESULT_LIMIT"] == "100"
    assert {item["key"]:item.get("value") for item in service["envVars"]}["PUBLIC_DEMO_ENABLED"] == "true"
    assert not any(item["key"] == "OPENAI_API_KEY" and item.get("value") for item in service["envVars"])


def test_ephemeral_restart_returns_identical_results_without_database_file():
    request = AnalyticsRequest()
    one = Engine(memory="512MB").metric(request,request.current)[0][0].value
    two = Engine(memory="512MB").metric(request,request.current)[0][0].value
    assert one == two
    assert not list((ROOT / "data").rglob("*.duckdb"))


def test_production_config_requires_auth_and_clean_source_restarts():
    service = yaml.safe_load((ROOT / "render.yaml").read_text())["services"][0]
    assert {item["key"]:item.get("value") for item in service["envVars"]}["APP_ENV"] == "production"
    configuration = tomllib.loads((ROOT / ".streamlit" / "config.toml").read_text())
    assert configuration["server"]["fileWatcherType"] == "none"
    assert "/etc/secrets/secrets.toml" in configuration["secrets"]["files"]


def test_smoke_restarts_same_port_after_real_health_request(tmp_path, monkeypatch):
    from scripts import smoke_deployment

    (tmp_path / "app.py").write_text("import streamlit as st\nst.write('Restart check')\n", encoding="utf-8")
    monkeypatch.setattr(smoke_deployment, "PROJECT_ROOT", tmp_path)
    with socket.socket() as reserve:
        reserve.bind(("127.0.0.1", 0))
        port = reserve.getsockname()[1]
    result = smoke_deployment.smoke(port)
    assert result["status"] == "pass"
    assert [start["restart"] for start in result["starts"]] == [0, 1]
    assert all(start["http_status"] == 200 and start["health"] == "ok" for start in result["starts"])
    assert result["persistent_storage_required"] is False
