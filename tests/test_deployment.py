from pathlib import Path
import yaml
import tomllib
from analytics_agent.engine import Engine
from analytics_agent.models import AnalyticsRequest

ROOT = Path(__file__).resolve().parents[1]


def test_render_configuration_uses_assigned_port_and_bundled_data():
    service = yaml.safe_load((ROOT / "render.yaml").read_text())["services"][0]
    assert service["type"] == "web"
    assert "--server.address 0.0.0.0" in service["startCommand"]
    assert "--server.port $PORT" in service["startCommand"]
    assert service["healthCheckPath"] == "/_stcore/health"
    assert "disk" not in service and service["autoDeploy"] is False
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
