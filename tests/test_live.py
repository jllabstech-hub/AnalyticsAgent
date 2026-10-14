"""Opt-in live tests. Cloud testing requires explicit invocation and credentials."""
import os
import pytest
from analytics_agent.config import load_settings
from analytics_agent.providers import manager_from_settings


@pytest.mark.skipif(os.getenv("RUN_LIVE_OLLAMA") != "1", reason="Live Ollama opt-in disabled; local diagnostic reports endpoint unavailable")
def test_live_ollama_inference():
    status = manager_from_settings(load_settings()).providers["ollama"].test_connection()
    assert status["inference_verified"]


@pytest.mark.skipif(os.getenv("RUN_LIVE_OPENAI") != "1", reason="Live OpenAI opt-in disabled for this test run")
def test_live_openai_inference():
    status = manager_from_settings(load_settings()).providers["openai"].test_connection()
    assert status["inference_verified"]
