from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from analytics_agent.providers import ModelReply, OpenAIProvider, ProviderError, ProviderManager
from analytics_agent.skills import ToolArguments


def fake_provider(name):
    provider = Mock(name=name)
    provider.health.return_value = {"reachable":True,"model_available":True}
    provider.chat.return_value = ModelReply(model="test",content="OK",latency_ms=1)
    return provider


@pytest.mark.parametrize("selected", ["ollama", "openai"])
def test_explicit_provider_switching(selected):
    ollama, cloud = fake_provider("ollama"), fake_provider("openai")
    manager = ProviderManager(ollama, cloud, selected)
    manager.chat([])
    assert manager.actual_provider == selected
    manager.providers[selected].chat.assert_called_once()
    manager.providers["openai" if selected == "ollama" else "ollama"].chat.assert_not_called()


@pytest.mark.parametrize("code", ["missing_key","timeout","connection","service"])
def test_openai_fallback_only_when_local_model_is_reachable(code):
    ollama, cloud = fake_provider("ollama"), fake_provider("openai")
    cloud.chat.side_effect = ProviderError(code,"safe failure",True)
    manager = ProviderManager(ollama, cloud, "openai")
    manager.chat([])
    assert manager.actual_provider == "ollama" and manager.last_fallback_reason == code


@pytest.mark.parametrize("code", ["authentication","invalid_request","invalid_response"])
def test_authentication_and_invalid_requests_never_fallback(code):
    ollama, cloud = fake_provider("ollama"), fake_provider("openai")
    cloud.chat.side_effect = ProviderError(code,"safe failure")
    with pytest.raises(ProviderError):
        ProviderManager(ollama, cloud, "openai").chat([])
    ollama.health.assert_not_called()
    ollama.chat.assert_not_called()


def test_local_failure_never_invokes_cloud():
    ollama, cloud = fake_provider("ollama"), fake_provider("openai")
    ollama.chat.side_effect = ProviderError("timeout","local timeout",True)
    with pytest.raises(ProviderError):
        ProviderManager(ollama,cloud).chat([])
    cloud.chat.assert_not_called()


def test_both_unavailable_and_disabled_fallback():
    ollama, cloud = fake_provider("ollama"), fake_provider("openai")
    cloud.chat.side_effect = ProviderError("missing_key","missing",True)
    ollama.health.side_effect = ProviderError("connection","offline",True)
    with pytest.raises(ProviderError, match="fallback is unavailable"):
        ProviderManager(ollama,cloud,"openai").chat([])
    with pytest.raises(ProviderError, match="missing"):
        ProviderManager(ollama,cloud,"openai",False).chat([])
    ollama.chat.assert_not_called()


def test_openai_sdk_tool_response_is_validated():
    client = Mock()
    function = SimpleNamespace(name="K1", arguments='{"request":{"metric":"mau"}}')
    message = SimpleNamespace(content=None, tool_calls=[SimpleNamespace(function=function,id="call-1")])
    client.chat.completions.create.return_value = SimpleNamespace(model="gpt-4.1-mini",choices=[SimpleNamespace(message=message)])
    reply = OpenAIProvider(client=client).chat([])
    assert ToolArguments.model_validate(reply.tool_calls[0].arguments).request.metric == "mau"


def test_missing_key_does_not_make_network_calls():
    with pytest.raises(ProviderError) as raised:
        OpenAIProvider().chat([])
    assert raised.value.code == "missing_key"


def test_explicit_openai_selection_works_without_ollama_endpoint(monkeypatch):
    from analytics_agent.config import Settings
    from analytics_agent import providers

    cloud = fake_provider("openai")
    monkeypatch.setattr(providers, "OpenAIProvider", lambda *args: cloud)
    settings = Settings(app_title="Test", openai_model="test", openai_api_key="", ollama_base_url="")
    manager = providers.manager_from_settings(settings, selected="openai")
    try:
        assert manager.chat([]).content == "OK"
        assert manager.actual_provider == "openai"
        cloud.chat.assert_called_once()
    finally:
        manager.close()


def test_fallback_stays_local_for_the_remainder_of_an_answer():
    ollama, cloud = fake_provider("ollama"), fake_provider("openai")
    cloud.chat.side_effect = ProviderError("timeout","temporary",True)
    manager = ProviderManager(ollama,cloud,"openai")
    manager.chat([])
    manager.chat([])
    assert cloud.chat.call_count == 1 and ollama.chat.call_count == 2


def test_actual_sdk_authentication_error_is_redacted_and_never_falls_back():
    import httpx2
    from openai import AuthenticationError
    client = Mock()
    response = httpx2.Response(401,request=httpx2.Request("POST","https://api.openai.com/v1/chat/completions"))
    client.chat.completions.create.side_effect = AuthenticationError("fictional-secret-in-error",response=response,body={})
    ollama = fake_provider("ollama")
    manager = ProviderManager(ollama,OpenAIProvider(client=client),"openai")
    with pytest.raises(ProviderError) as raised: manager.chat([])
    assert raised.value.code == "authentication"
    assert "fictional-secret" not in str(raised.value)
    ollama.chat.assert_not_called()


def test_owned_network_clients_are_closed(monkeypatch):
    from analytics_agent.providers import OllamaProvider
    session = Mock()
    monkeypatch.setattr("analytics_agent.providers.requests.Session",lambda:session)
    provider = OllamaProvider()
    manager = ProviderManager(provider,OpenAIProvider())
    manager.close()
    session.close.assert_called_once()


def test_injected_sdk_client_remains_owned_by_the_caller():
    client = Mock()
    provider = OpenAIProvider(client=client)
    provider.close()
    client.close.assert_not_called()
