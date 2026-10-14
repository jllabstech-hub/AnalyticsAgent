"""The opt-in public demo never grants access to paid or local LLMs."""
from unittest.mock import Mock
import pytest
from streamlit.testing.v1 import AppTest
from analytics_agent.config import PROJECT_ROOT, load_settings
from analytics_agent.agent import AnalyticsAgent
from analytics_agent.providers import ProviderError, manager_from_settings

APP = str(PROJECT_ROOT / "app.py")


@pytest.mark.parametrize("enabled, expected", [("true", True), ("false", False)])
def test_public_demo_is_explicit_server_configuration(monkeypatch, tmp_path, enabled, expected):
    monkeypatch.setenv("PUBLIC_DEMO_ENABLED", enabled)
    assert load_settings(tmp_path / "missing.env").public_demo_enabled is expected


def test_malformed_public_demo_configuration_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("PUBLIC_DEMO_ENABLED", "yes")
    with pytest.raises(ValueError, match="PUBLIC_DEMO_ENABLED"):
        load_settings(tmp_path / "missing.env")


@pytest.mark.parametrize("provider", ["ollama", "openai"])
def test_public_demo_rejects_provider_connections_before_network(monkeypatch, provider):
    monkeypatch.setenv("PUBLIC_DEMO_ENABLED", "true")
    settings = load_settings()
    with pytest.raises(ProviderError) as error:
        manager_from_settings(settings, selected=provider)
    assert error.value.code == "authorization" and not error.value.recoverable
    manager = Mock(last_fallback_reason=None)
    answer = AnalyticsAgent(settings=settings).run("Compare August and September active users.", mode=provider, manager=manager)
    assert answer.status == "error" and answer.tool_calls == 0 and not answer.results
    manager.chat.assert_not_called()


def test_anonymous_hosted_demo_executes_real_queries_without_llm(monkeypatch):
    from analytics_agent import ui
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PUBLIC_DEMO_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "fictional-private-server-marker")
    monkeypatch.setenv("DUCKDB_MEMORY_LIMIT", "320MB")
    monkeypatch.setenv("RESULT_LIMIT", "100")
    forbidden = Mock(side_effect=AssertionError("Public demo attempted an LLM connection"))
    monkeypatch.setattr(ui, "manager_from_settings", forbidden)
    app = AppTest.from_file(APP, default_timeout=60).run()
    assert not app.exception and app.chat_input and not app.error
    assert app.toggle(key="demo_mode").value and app.toggle(key="demo_mode").disabled
    assert "Settings" not in app.selectbox(key="page").options
    assert not any(button.label == "LLM Settings" for button in app.button)
    assert any("Public synthetic demo" in info.value for info in app.info)
    # A stale provider preference must not reopen cloud access.
    app.session_state["demo_mode"] = False
    app.session_state["selected_provider"] = "openai"
    app.chat_input[0].set_value("Compare August and September active users.").run()
    answer = app.session_state["last_answer"]
    assert not app.exception and answer.status == "ok" and answer.provider == "deterministic demo"
    assert answer.results[0].baseline == 66025 and answer.results[0].current == 65292
    assert answer.results[0].evidence and answer.tool_calls == 1
    assert "fictional-private-server-marker" not in str(app.session_state)
    forbidden.assert_not_called()
    app.selectbox(key="page").select("Data Explorer").run()
    assert not app.exception and app.metric[0].value == "100,000"


@pytest.mark.parametrize("alternate", [True, False])
def test_public_demo_cannot_expose_an_unmarked_or_alternative_warehouse(monkeypatch, tmp_path, alternate):
    from analytics_agent import ui
    from analytics_agent.engine import Engine
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PUBLIC_DEMO_ENABLED", "true")
    if alternate:
        (tmp_path / "manifest.json").write_text('{"is_synthetic": true}')
        monkeypatch.setattr(ui, "analytical_engine", lambda _: Engine(data_dir=tmp_path))
    else:
        from pathlib import Path
        original_read = Path.read_text
        public_manifest = PROJECT_ROOT / "data" / "synthetic" / "manifest.json"
        monkeypatch.setattr(Path, "read_text", lambda path, *args, **kwargs: '{"is_synthetic": false}' if path == public_manifest else original_read(path, *args, **kwargs))
    app = AppTest.from_file(APP).run()
    assert not app.exception and not app.chat_input and not app.metric
    assert any("Public demo data validation failed" in error.value for error in app.error)


def test_public_mode_change_clears_private_conversation(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PUBLIC_DEMO_ENABLED", "true")
    app = AppTest.from_file(APP).run()
    app.session_state["access_fingerprint"] = "private_identity"
    app.session_state["messages"] = [{"role": "assistant", "content": "private conversation marker"}]
    app.session_state["last_answer"] = "private result marker"
    app.session_state["connection_status"] = {"inference_verified": True}
    app.run()
    assert not app.exception and app.session_state["messages"] == []
    assert "last_answer" not in app.session_state and "connection_status" not in app.session_state


def test_private_production_still_requires_sign_in_when_demo_disabled(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("PUBLIC_DEMO_ENABLED", "false")
    app = AppTest.from_file(APP).run()
    assert not app.exception and not app.chat_input and not app.metric and not app.radio
    assert any("Production access is disabled" in error.value for error in app.error)
