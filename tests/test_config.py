from analytics_agent.config import DEFAULT_APP_TITLE, load_settings


def clear_settings(monkeypatch):
    for name in ("APP_TITLE", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)


def test_setup_works_without_env_file_or_api_key(tmp_path, monkeypatch):
    clear_settings(monkeypatch)
    settings = load_settings(tmp_path / "missing.env")

    assert settings.app_title == DEFAULT_APP_TITLE
    assert settings.openai_api_key == ""
    assert settings.openai_model == "gpt-4.1-mini"


def test_dotenv_loads_settings_without_revealing_secret(tmp_path, monkeypatch):
    clear_settings(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_TITLE=Demo Analytics\nOPENAI_API_KEY=synthetic-test-key\n"
        "OPENAI_MODEL=test-model\n",
        encoding="utf-8",
    )
    # Restore the environment after dotenv populates it.
    for name in ("APP_TITLE", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)

    settings = load_settings(env_file)

    assert settings.app_title == "Demo Analytics"
    assert settings.openai_api_key == "synthetic-test-key"
    assert settings.openai_model == "test-model"
    assert "synthetic-test-key" not in repr(settings)


def test_environment_variables_take_priority_over_dotenv(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("APP_TITLE=Local title\nOPENAI_API_KEY=local-test-key\n", encoding="utf-8")
    monkeypatch.setenv("APP_TITLE", "Hosted title")
    monkeypatch.setenv("OPENAI_API_KEY", "hosted-test-key")
    monkeypatch.setenv("OPENAI_MODEL", "")

    settings = load_settings(env_file)

    assert settings.app_title == "Hosted title"
    assert settings.openai_api_key == "hosted-test-key"
