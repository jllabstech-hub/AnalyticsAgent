from pathlib import Path
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_deterministic_chat_displays_computed_kpis(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert app.session_state["selected_provider"] == "ollama"
    assert app.session_state["demo_mode"] is False
    app.toggle(key="demo_mode").set_value(True).run()
    app.chat_input[0].set_value("Compare August and September active users.").run()
    assert not app.exception
    assert app.session_state["last_answer"].status == "ok"
    assert app.metric[0].value == "66,025"
    assert app.metric[1].value == "65,292"


def test_settings_switch_and_explorer_are_functional():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.selectbox(key="page").select("Settings").run()
    assert not app.exception
    app.radio(key="_selected_provider").set_value("openai").run()
    assert app.session_state["selected_provider"] == "openai"
    assert not app.exception
    app.selectbox(key="page").select("Data Explorer").run()
    assert not app.exception
    assert app.metric[0].value == "100,000"


def test_provider_preferences_survive_navigation_and_reruns():
    app = AppTest.from_file(APP, default_timeout=30).run()
    app.selectbox(key="page").select("Settings").run()
    app.radio(key="_selected_provider").set_value("openai").run()
    app.selectbox(key="_ollama_model").select("qwen3:1.7b").run()
    app.toggle(key="_automatic_fallback").set_value(False).run()
    app.selectbox(key="page").select("Data Explorer").run()
    app.selectbox(key="page").select("Analytics Workspace").run()
    app.run()
    assert app.session_state["selected_provider"] == "openai"
    assert app.session_state["ollama_model"] == "qwen3:1.7b"
    assert app.session_state["automatic_fallback"] is False
    assert not app.exception


def test_server_credentials_never_enter_session_or_rendered_text(monkeypatch):
    secret = "fictional-api-secret-marker"
    monkeypatch.setenv("OPENAI_API_KEY",secret)
    app = AppTest.from_file(APP,default_timeout=30).run()
    app.selectbox(key="page").select("Settings").run()
    assert secret not in str(app.session_state)
    assert secret not in " ".join(x.value for x in app.markdown)
    assert not app.exception


def test_provisional_results_warn_above_kpis_and_preserve_chart_gaps(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app = AppTest.from_file(APP,default_timeout=30).run()
    app.toggle(key="demo_mode").set_value(True).run()
    app.chat_input[0].set_value("Compare August and September active users for all users in the incomplete scenario.").run()
    assert not app.exception
    answer = app.session_state["last_answer"]
    assert answer.status == "ok" and not answer.results[0].quality["complete"]
    assert any("Provisional results" in warning.value for warning in app.warning)
    assert all(row["active_users"] is None for row in answer.results[0].trend[-7:])


def test_invalid_server_limits_do_not_expose_a_traceback(monkeypatch):
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS","nan")
    app = AppTest.from_file(APP).run()
    assert not app.exception and not app.chat_input
    assert "Server configuration is invalid" in app.error[0].value


def test_latest_connection_fallback_reason_overrides_earlier_demo_answer(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from analytics_agent import ui
    from analytics_agent.providers import ProviderError
    manager = Mock(last_fallback_reason="missing_key")
    manager.test_connection.side_effect = ProviderError("both_unavailable","Safe connection failure")
    monkeypatch.setattr(ui,"manager_from_settings",lambda *args:manager)
    app = AppTest.from_file(APP,default_timeout=30).run()
    app.selectbox(key="page").select("Settings").run()
    app.session_state["last_answer"] = SimpleNamespace(provider="deterministic demo",fallback_reason=None)
    next(button for button in app.button if button.label == "Test Connection").click().run()
    assert not app.exception
    assert any(caption.value == "Last fallback reason: missing_key" for caption in app.caption)
