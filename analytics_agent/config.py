"""Read local configuration without overriding deployment environment variables."""

import os
import math
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APP_TITLE = "BDC Analytics Agent"


@dataclass(frozen=True)
class Settings:
    app_title: str
    openai_model: str
    openai_api_key: str = field(repr=False)
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:8b"
    ollama_api_token: str = field(default="", repr=False)
    fallback_to_ollama: bool = True
    llm_timeout: float = 30
    max_tool_calls: int = 6
    investigation_depth: int = 3
    investigation_timeout: float = 120
    result_limit: int = 500
    app_env: str = "local"


def load_settings(env_file: Path | None = None) -> Settings:
    """Load an optional .env file; an API key is not required for Phase 1."""
    load_dotenv(env_file if env_file is not None else PROJECT_ROOT / ".env", override=False)
    provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
    if provider not in ("ollama", "openai"):
        raise ValueError("LLM_PROVIDER must be ollama or openai.")
    app_env = "production" if os.getenv("RENDER", "").lower() == "true" else os.getenv("APP_ENV", "local").strip().lower()
    if app_env not in ("local","production"):
        raise ValueError("APP_ENV must be local or production.")
    settings = Settings(
        app_title=os.getenv("APP_TITLE", "").strip() or DEFAULT_APP_TITLE,
        openai_model=os.getenv("OPENAI_MODEL", "").strip() or "gpt-4.1-mini",
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        llm_provider=provider,
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip(),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen3:8b").strip() or "qwen3:8b",
        ollama_api_token=os.getenv("OLLAMA_API_TOKEN", "").strip(),
        fallback_to_ollama=os.getenv("OPENAI_FALLBACK_TO_OLLAMA", "true").lower() == "true",
        llm_timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
        max_tool_calls=int(os.getenv("MAX_TOOL_CALLS", "6")),
        investigation_depth=int(os.getenv("INVESTIGATION_DEPTH", "3")),
        investigation_timeout=float(os.getenv("INVESTIGATION_TIMEOUT_SECONDS", "120")),
        result_limit=int(os.getenv("RESULT_LIMIT", "500")),
        app_env=app_env,
    )
    limits = (settings.llm_timeout, settings.max_tool_calls, settings.investigation_depth, settings.investigation_timeout, settings.result_limit)
    if any(not math.isfinite(value) or value <= 0 for value in limits):
        raise ValueError("Execution limits must be finite and positive.")
    return settings
