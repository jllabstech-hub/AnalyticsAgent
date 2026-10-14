"""Server-side provider adapters. Model output is untrusted input, never evidence."""
import json
import time
from typing import Protocol
from urllib.parse import urlsplit
import requests
from pydantic import Field
from analytics_agent.models import Contract


class ProviderError(Exception):
    def __init__(self, code, message, recoverable=False):
        super().__init__(message)
        self.code, self.recoverable = code, recoverable


class ToolCall(Contract):
    name: str
    arguments: dict
    call_id: str = ""


class ModelReply(Contract):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    model: str
    latency_ms: float


class Provider(Protocol):
    name: str
    model: str
    def health(self) -> dict: ...
    def chat(self, messages, tools=None, schema=None) -> ModelReply: ...


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url="http://localhost:11434", model="qwen3:8b", timeout=30, token="", session=None):
        if not isinstance(base_url, str):
            raise ValueError("Invalid Ollama endpoint.")
        if base_url:
            url = urlsplit(base_url)
            local = url.hostname in ("localhost", "127.0.0.1", "::1")
            if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
                raise ValueError("Use an Ollama origin without credentials, path, query or fragment.")
            if url.scheme not in ("http", "https") or not url.hostname:
                raise ValueError("Invalid Ollama endpoint.")
            if url.hostname.endswith("ollama.com"):
                raise ValueError("Ollama cloud endpoints are not local processing.")
            if not local and (url.scheme != "https" or not token):
                raise ValueError("Remote Ollama requires HTTPS and a server-side authorization token.")
        self.base_url, self.model, self.timeout = base_url.rstrip("/"), model, timeout
        self._token, self._session = token, session or requests.Session()
        self._owns_session = session is None

    def close(self):
        if self._owns_session: self._session.close()

    def _request(self, method, path, body=None):
        if not self.base_url:
            raise ProviderError("configuration", "Ollama endpoint is not configured. Configure a secured reachable endpoint or select deterministic demo mode.")
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        try:
            response = self._session.request(method, self.base_url + path, json=body, headers=headers,
                timeout=(min(5, self.timeout/4), self.timeout*.75), allow_redirects=False)
            if response.status_code in (401, 403):
                raise ProviderError("authentication", "Ollama authorization failed.")
            if response.status_code >= 500:
                raise ProviderError("service", "Ollama service failed.", True)
            if response.status_code != 200:
                raise ProviderError("invalid_request", "Ollama rejected the request or model is unavailable.")
            if len(response.content) > 1_000_000:
                raise ProviderError("invalid_response", "Ollama response exceeded the limit.")
            return response.json()
        except requests.Timeout:
            raise ProviderError("timeout", "Ollama request timed out.", True) from None
        except requests.RequestException:
            raise ProviderError("connection", "Ollama is not reachable. Select deterministic demo mode or configure Ollama.", True) from None
        except (ValueError, KeyError, TypeError):
            raise ProviderError("invalid_response", "Ollama returned an invalid response.") from None

    def models(self):
        response = self._request("GET", "/api/tags")
        try:
            entries = response["models"]
            if not isinstance(entries,list) or len(entries)>1000: raise ValueError("Invalid discovery list")
            names = [item["name"] for item in entries]
            if any(not isinstance(name,str) or not name or len(name)>200 for name in names): raise ValueError("Invalid model name")
            return names
        except (ValueError,KeyError,TypeError):
            raise ProviderError("invalid_response","Ollama returned an invalid model list.") from None

    def health(self):
        models = self.models()
        available = self.model in models
        return {"provider": self.name, "reachable": True, "model": self.model,
                "model_available": available, "models": models, "inference_verified": False}

    def metadata(self):
        return self._request("POST", "/api/show", {"model": self.model})

    def chat(self, messages, tools=None, schema=None):
        payload = {"model": self.model, "messages": messages, "stream": False, "options": {"temperature": 0, "num_predict": 2048}}
        if tools:
            payload["tools"] = tools
        if schema:
            payload["format"] = schema
        started = time.perf_counter()
        raw = self._request("POST", "/api/chat", payload)
        try:
            message = raw["message"]
            calls = [ToolCall(name=c["function"]["name"], arguments=c["function"]["arguments"], call_id=str(c.get("id", ""))) for c in message.get("tool_calls", [])]
            return ModelReply(content=message.get("content", ""), tool_calls=calls, model=raw.get("model", self.model), latency_ms=(time.perf_counter()-started)*1000)
        except (ValueError, KeyError, TypeError):
            raise ProviderError("invalid_response", "Ollama returned invalid tool-call arguments.") from None

    def structured(self, messages, result_model):
        reply = self.chat(messages, schema=result_model.model_json_schema())
        return result_model.model_validate_json(reply.content)

    def test_connection(self):
        status = self.health()
        if not status["model_available"]:
            raise ProviderError("model_missing", "Configured Ollama model is not installed.")
        reply = self.chat([{"role": "user", "content": "Reply with OK."}])
        if not reply.content.strip():
            raise ProviderError("invalid_response", "Inference returned no text.")
        return {**status, "inference_verified": True, "latency_ms": reply.latency_ms}


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key="", model="gpt-4.1-mini", timeout=30, client=None):
        self.model, self.timeout = model, timeout
        self._configured = bool(api_key) or client is not None
        self._client = client
        self._owns_client = client is None
        if api_key and client is None:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key, timeout=timeout, max_retries=0)

    def close(self):
        if self._owns_client and self._client is not None: self._client.close()

    def health(self):
        # A configured secret is not evidence of connectivity; no billed calls here.
        return {"provider": self.name, "model": self.model, "configured": self._configured,
                "reachable": None, "inference_verified": False}

    def chat(self, messages, tools=None, schema=None):
        if not self._configured:
            raise ProviderError("missing_key", "OpenAI API key is missing.", True)
        from openai import AuthenticationError, PermissionDeniedError, APITimeoutError, APIConnectionError, RateLimitError, InternalServerError, APIStatusError
        started = time.perf_counter()
        parameters = {"model": self.model, "messages": messages, "temperature": 0, "max_completion_tokens": 2048}
        if tools:
            parameters["tools"] = tools
        if schema:
            parameters["response_format"] = {"type":"json_schema", "json_schema":{"name":"validated_result", "schema":schema}}
        try:
            raw = self._client.chat.completions.create(**parameters, timeout=self.timeout)
            message = raw.choices[0].message
            calls = [ToolCall(name=c.function.name, arguments=json.loads(c.function.arguments), call_id=c.id) for c in message.tool_calls or []]
            return ModelReply(content=message.content or "", tool_calls=calls, model=raw.model, latency_ms=(time.perf_counter()-started)*1000)
        except (AuthenticationError, PermissionDeniedError):
            raise ProviderError("authentication", "OpenAI authentication or authorization failed.") from None
        except APITimeoutError:
            raise ProviderError("timeout", "OpenAI request timed out.", True) from None
        except APIConnectionError:
            raise ProviderError("connection", "OpenAI service is unreachable.", True) from None
        except (RateLimitError, InternalServerError):
            raise ProviderError("service", "OpenAI temporary service failure.", True) from None
        except APIStatusError:
            raise ProviderError("invalid_request", "OpenAI rejected the configuration or request.") from None
        except (ValueError, KeyError, TypeError, AttributeError):
            raise ProviderError("invalid_response", "OpenAI returned invalid structured arguments.") from None

    def test_connection(self):
        reply = self.chat([{"role":"user", "content":"Reply with OK."}])
        if not reply.content.strip():
            raise ProviderError("invalid_response", "OpenAI inference returned no text.")
        return {**self.health(), "reachable": True, "inference_verified": True, "latency_ms": reply.latency_ms}


class ProviderManager:
    """One manager per request/session; fallback is never local-to-cloud."""
    def __init__(self, ollama: Provider, openai: Provider, selected="ollama", fallback=True):
        if selected not in ("ollama", "openai"):
            raise ValueError("Unknown provider.")
        self.providers = {"ollama":ollama, "openai":openai}
        self.selected, self.fallback = selected, fallback
        self.actual_provider, self.last_fallback_reason = selected, None
        self.deadline = None

    def close(self):
        for provider in self.providers.values():
            close = getattr(provider,"close",None)
            if callable(close): close()

    def _budget(self, name):
        if self.deadline is not None:
            remaining = self.deadline-time.perf_counter()
            if remaining <= 0: raise ProviderError("execution_timeout","Investigation deadline exceeded.")
            provider = self.providers[name]
            if isinstance(getattr(provider,"timeout",None),(int,float)):
                provider.timeout = min(provider.timeout,remaining*.9)

    def chat(self, messages, tools=None, schema=None):
        if self.last_fallback_reason is not None and self.actual_provider == "ollama":
            self._budget("ollama")
            return self.providers["ollama"].chat(messages,tools,schema)
        try:
            self._budget(self.selected)
            reply = self.providers[self.selected].chat(messages, tools, schema)
            self.actual_provider = self.selected
            return reply
        except ProviderError as error:
            if self.selected != "openai" or not self.fallback or not error.recoverable or error.code not in ("missing_key", "timeout", "connection", "service"):
                raise
            self.last_fallback_reason = error.code
            try:
                self._budget("ollama")
                status = self.providers["ollama"].health()
                if not status.get("reachable") or not status.get("model_available"):
                    raise ProviderError("unavailable", "Ollama fallback model is unavailable.")
                self._budget("ollama")
                reply = self.providers["ollama"].chat(messages, tools, schema)
            except ProviderError:
                raise ProviderError("both_unavailable", "Selected OpenAI failed and Ollama fallback is unavailable. Select deterministic demo mode.") from None
            self.actual_provider, self.last_fallback_reason = "ollama", error.code
            return reply

    def test_connection(self):
        reply = self.chat([{"role":"user","content":"Reply with OK."}])
        if not reply.content.strip(): raise ProviderError("invalid_response","Inference returned no text.")
        try: metadata = self.providers[self.actual_provider].health()
        except ProviderError: metadata = {}
        return {**metadata,"provider":self.actual_provider,"model":reply.model,"reachable":True,"inference_verified":True,
                "latency_ms":reply.latency_ms,"fallback_reason":self.last_fallback_reason}


def manager_from_settings(settings, selected=None, ollama_model=None, openai_model=None, fallback=None, timeout=None):
    timeout = timeout or settings.llm_timeout
    return ProviderManager(
        OllamaProvider(settings.ollama_base_url, ollama_model or settings.ollama_model, timeout, settings.ollama_api_token),
        OpenAIProvider(settings.openai_api_key, openai_model or settings.openai_model or "gpt-4.1-mini", timeout),
        selected or settings.llm_provider, settings.fallback_to_ollama if fallback is None else fallback)
