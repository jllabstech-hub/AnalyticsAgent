from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_application_renders_without_api_key(monkeypatch):
    monkeypatch.setenv("APP_TITLE", "BDC Analytics Agent")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_MODEL", "")
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()

    assert not app.exception
    assert app.title[0].value == "BDC Analytics Agent"
    assert not app.chat_input[0].disabled
    assert app.info[0].value == "Ask a question to calculate results from the synthetic warehouse."
    assert len(app.metric) == 0
