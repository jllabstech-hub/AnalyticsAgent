import json
from unittest.mock import Mock
import pytest
import requests
from pydantic import ValidationError
from analytics_agent.models import AnalyticsRequest
from analytics_agent.providers import OllamaProvider, ProviderError
from analytics_agent.skills import ToolArguments


def response(body, status=200):
    return Mock(status_code=status, content=json.dumps(body).encode(), json=lambda: body)


def test_realistic_ollama_tool_call_is_validated_before_execution():
    session = Mock()
    session.request.return_value = response({"model":"qwen3:8b", "message":{"tool_calls":[{"function":{"name":"K1", "arguments":{"request":AnalyticsRequest().model_dump(mode="json")}}}]}})
    provider = OllamaProvider(session=session)
    reply = provider.chat([{"role":"user","content":"Compare active users"}], tools=[])
    assert ToolArguments.model_validate(reply.tool_calls[0].arguments).request.metric == "mau"
    assert session.request.call_args.kwargs["json"]["stream"] is False


def test_malformed_tool_arguments_are_rejected():
    with pytest.raises(ValidationError):
        ToolArguments.model_validate({"request":{"metric":"mau"}, "sql":"select secret"})


def test_models_health_and_actual_inference_diagnostic():
    session = Mock()
    session.request.side_effect = [response({"models":[{"name":"qwen3:8b"}]}), response({"message":{"content":"OK"}})]
    status = OllamaProvider(session=session).test_connection()
    assert status["inference_verified"] and status["model_available"]


@pytest.mark.parametrize("failure,code", [(requests.Timeout(),"timeout"),(requests.ConnectionError(),"connection")])
def test_ollama_transport_failures(failure, code):
    session = Mock()
    session.request.side_effect = failure
    with pytest.raises(ProviderError) as raised:
        OllamaProvider(session=session).chat([])
    assert raised.value.code == code


def test_structured_outputs_are_validated():
    session = Mock()
    session.request.return_value = response({"message":{"content":AnalyticsRequest().model_dump_json()}})
    assert OllamaProvider(session=session).structured([], AnalyticsRequest).metric == "mau"


def test_remote_ollama_requires_secured_endpoint():
    with pytest.raises(ValueError):
        OllamaProvider("http://public.example:11434")
    with pytest.raises(ValueError):
        OllamaProvider("https://remote.example")
    with pytest.raises(ValueError):
        OllamaProvider("https://ollama.com", token="test-token")


def test_unconfigured_ollama_fails_safely_without_network():
    session = Mock()
    provider = OllamaProvider("", session=session)
    for operation in (provider.health, lambda: provider.chat([]), provider.test_connection, provider.metadata):
        with pytest.raises(ProviderError) as raised:
            operation()
        assert raised.value.code == "configuration"
    session.request.assert_not_called()


@pytest.mark.parametrize("body", [[],{"models":"malformed"},{"models":[{}]}])
def test_malformed_model_discovery_is_a_safe_provider_error(body):
    session = Mock()
    session.request.return_value = response(body)
    with pytest.raises(ProviderError) as raised: OllamaProvider(session=session).health()
    assert raised.value.code == "invalid_response"
