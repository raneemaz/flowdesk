import io
import json
import urllib.error

import pytest

from app.ai.providers import (
    AICompletionRequest,
    AICompletionResponse,
    AIProvider,
    AIProviderAuthenticationError,
    AIProviderRateLimitError,
    AIProviderRequestError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    AIToolCompletionResponse,
    AIToolDefinition,
    AnthropicProvider,
    _send_anthropic_request,
    complete_with_retries,
    complete_with_tools_with_retries,
)


def _anthropic_response(text="hello"):
    return {
        "content": [{"type": "text", "text": text}],
        "model": "claude-haiku-5-5",
        "usage": {"input_tokens": 10, "output_tokens": 5},
    }


# --- AnthropicProvider.complete (request_fn injected - no real network) ----


def test_complete_returns_a_well_formed_response():
    provider = AnthropicProvider(
        api_key="key", model="claude-haiku-5-5", request_fn=lambda *a: _anthropic_response("Hello world")
    )

    response = provider.complete(AICompletionRequest(system_prompt="sys", user_prompt="user"), timeout_seconds=5)

    assert response.text == "Hello world"
    assert response.model == "claude-haiku-5-5"
    assert response.input_tokens == 10
    assert response.output_tokens == 5


def test_complete_concatenates_multiple_text_blocks():
    body = {"content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}], "model": "m", "usage": {}}
    provider = AnthropicProvider(api_key="key", model="m", request_fn=lambda *a: body)

    response = provider.complete(AICompletionRequest(system_prompt="sys", user_prompt="user"), timeout_seconds=5)

    assert response.text == "ab"


def test_complete_raises_response_error_on_missing_content_key():
    provider = AnthropicProvider(api_key="key", model="m", request_fn=lambda *a: {"model": "m"})

    with pytest.raises(AIProviderResponseError):
        provider.complete(AICompletionRequest(system_prompt="sys", user_prompt="user"), timeout_seconds=5)


def test_complete_raises_response_error_when_body_is_not_a_dict():
    provider = AnthropicProvider(api_key="key", model="m", request_fn=lambda *a: ["not", "a", "dict"])

    with pytest.raises(AIProviderResponseError):
        provider.complete(AICompletionRequest(system_prompt="sys", user_prompt="user"), timeout_seconds=5)


def test_constructor_requires_an_api_key():
    with pytest.raises(AIProviderAuthenticationError):
        AnthropicProvider(api_key="", model="m")


def test_complete_passes_the_prompt_and_max_tokens_through_to_the_request_fn():
    captured = {}

    def fake_request_fn(api_key, payload, timeout_seconds):
        captured["api_key"] = api_key
        captured["payload"] = payload
        captured["timeout_seconds"] = timeout_seconds
        return _anthropic_response()

    provider = AnthropicProvider(api_key="secret-key", model="claude-haiku-5-5", request_fn=fake_request_fn)
    provider.complete(
        AICompletionRequest(system_prompt="be terse", user_prompt="summarize this", max_tokens=42), timeout_seconds=9
    )

    assert captured["api_key"] == "secret-key"
    assert captured["payload"]["system"] == "be terse"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "summarize this"}]
    assert captured["payload"]["max_tokens"] == 42
    assert captured["timeout_seconds"] == 9


# --- _send_anthropic_request (the real HTTP layer's error mapping) ---------


class _FakeHTTPResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_send_anthropic_request_returns_parsed_json_on_success(monkeypatch):
    monkeypatch.setattr(
        "app.ai.providers.urllib.request.urlopen", lambda *a, **k: _FakeHTTPResponse(_anthropic_response())
    )

    body = _send_anthropic_request("key", {"model": "m"}, 5)

    assert body["model"] == "claude-haiku-5-5"


@pytest.mark.parametrize(
    "status_code,expected_exc",
    [
        (401, AIProviderAuthenticationError),
        (403, AIProviderAuthenticationError),
        (429, AIProviderRateLimitError),
        (500, AIProviderUnavailableError),
        (503, AIProviderUnavailableError),
        (400, AIProviderRequestError),
        (422, AIProviderRequestError),
    ],
)
def test_send_anthropic_request_maps_http_status_codes(monkeypatch, status_code, expected_exc):
    def raise_http_error(*args, **kwargs):
        raise urllib.error.HTTPError(
            url="https://api.anthropic.com/v1/messages",
            code=status_code,
            msg="error",
            hdrs=None,
            fp=io.BytesIO(b'{"error": "details"}'),
        )

    monkeypatch.setattr("app.ai.providers.urllib.request.urlopen", raise_http_error)

    with pytest.raises(expected_exc):
        _send_anthropic_request("key", {"model": "m"}, 5)


def test_send_anthropic_request_maps_a_timeout(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("app.ai.providers.urllib.request.urlopen", raise_timeout)

    with pytest.raises(AIProviderTimeoutError):
        _send_anthropic_request("key", {"model": "m"}, 5)


def test_send_anthropic_request_maps_a_connection_failure(monkeypatch):
    def raise_url_error(*args, **kwargs):
        raise urllib.error.URLError("network is unreachable")

    monkeypatch.setattr("app.ai.providers.urllib.request.urlopen", raise_url_error)

    with pytest.raises(AIProviderUnavailableError):
        _send_anthropic_request("key", {"model": "m"}, 5)


def test_send_anthropic_request_maps_non_json_content(monkeypatch):
    class _BadResponse(_FakeHTTPResponse):
        def read(self):
            return b"not json"

    monkeypatch.setattr("app.ai.providers.urllib.request.urlopen", lambda *a, **k: _BadResponse({}))

    with pytest.raises(AIProviderResponseError):
        _send_anthropic_request("key", {"model": "m"}, 5)


# --- complete_with_retries ---------------------------------------------------


class _FlakyProvider(AIProvider):
    """Raises `error` for the first `fail_count` calls, then succeeds."""

    def __init__(self, error: Exception, fail_count: int):
        self._error = error
        self._fail_count = fail_count
        self.calls = 0

    def complete(self, request, *, timeout_seconds):
        self.calls += 1
        if self.calls <= self._fail_count:
            raise self._error
        return AICompletionResponse(text="ok", model="m", input_tokens=1, output_tokens=1)


class _AlwaysFailsProvider(AIProvider):
    def __init__(self, error: Exception):
        self._error = error
        self.calls = 0

    def complete(self, request, *, timeout_seconds):
        self.calls += 1
        raise self._error


def _sleep_recorder():
    calls = []

    def sleep_fn(seconds):
        calls.append(seconds)

    return calls, sleep_fn


def test_complete_with_retries_succeeds_after_transient_failures():
    provider = _FlakyProvider(AIProviderTimeoutError("slow"), fail_count=2)
    sleeps, sleep_fn = _sleep_recorder()

    response = complete_with_retries(
        provider,
        AICompletionRequest(system_prompt="s", user_prompt="u"),
        max_retries=2,
        backoff_seconds=1.0,
        sleep_fn=sleep_fn,
    )

    assert response.text == "ok"
    assert provider.calls == 3
    assert sleeps == [1.0, 2.0]  # exponential backoff: 1 * 2**0, 1 * 2**1


def test_complete_with_retries_raises_after_exhausting_retries():
    provider = _AlwaysFailsProvider(AIProviderRateLimitError("slow down"))
    _, sleep_fn = _sleep_recorder()

    with pytest.raises(AIProviderRateLimitError):
        complete_with_retries(
            provider, AICompletionRequest(system_prompt="s", user_prompt="u"), max_retries=2, sleep_fn=sleep_fn
        )

    assert provider.calls == 3  # initial attempt + 2 retries


@pytest.mark.parametrize("error_cls", [AIProviderAuthenticationError, AIProviderRequestError])
def test_complete_with_retries_never_retries_non_transient_errors(error_cls):
    provider = _AlwaysFailsProvider(error_cls("not retryable"))
    _, sleep_fn = _sleep_recorder()

    with pytest.raises(error_cls):
        complete_with_retries(
            provider, AICompletionRequest(system_prompt="s", user_prompt="u"), max_retries=5, sleep_fn=sleep_fn
        )

    assert provider.calls == 1  # no retry at all


# --- AIProvider.complete_with_tools (FD-061) - default + AnthropicProvider ---


_TOOLS = [AIToolDefinition(name="get_weather", description="Gets the weather", input_schema={"type": "object"})]


def test_complete_with_tools_default_raises_not_implemented():
    """A provider that never overrides complete_with_tools (every
    FD-055/057 fake provider in this test suite, and _AlwaysFailsProvider/
    _FlakyProvider above) must stay instantiable and usable for
    `complete` - only calling complete_with_tools on it fails."""
    provider = _AlwaysFailsProvider(AIProviderTimeoutError("irrelevant"))

    with pytest.raises(NotImplementedError):
        provider.complete_with_tools([], system_prompt="s", tools=_TOOLS, max_tokens=10, timeout_seconds=5)


def _anthropic_tool_use_response(tool_name="get_weather", tool_input=None, text=None):
    content = []
    if text is not None:
        content.append({"type": "text", "text": text})
    content.append({"type": "tool_use", "id": "toolu_1", "name": tool_name, "input": tool_input or {}})
    return {"content": content, "model": "claude-haiku-5-5", "usage": {"input_tokens": 3, "output_tokens": 2}}


def test_anthropic_complete_with_tools_parses_a_tool_use_response():
    provider = AnthropicProvider(
        api_key="key", model="m", request_fn=lambda *a: _anthropic_tool_use_response(tool_input={"city": "Paris"})
    )

    response = provider.complete_with_tools(
        [{"role": "user", "content": "weather?"}], system_prompt="sys", tools=_TOOLS, max_tokens=10, timeout_seconds=5
    )

    assert response.text is None
    assert len(response.tool_uses) == 1
    assert response.tool_uses[0].name == "get_weather"
    assert response.tool_uses[0].input == {"city": "Paris"}
    assert response.tool_uses[0].id == "toolu_1"


def test_anthropic_complete_with_tools_parses_a_final_text_only_response():
    provider = AnthropicProvider(api_key="key", model="m", request_fn=lambda *a: _anthropic_response("All done."))

    response = provider.complete_with_tools(
        [{"role": "user", "content": "weather?"}], system_prompt="sys", tools=_TOOLS, max_tokens=10, timeout_seconds=5
    )

    assert response.text == "All done."
    assert response.tool_uses == []


def test_anthropic_complete_with_tools_handles_both_text_and_a_tool_use_in_one_response():
    provider = AnthropicProvider(
        api_key="key",
        model="m",
        request_fn=lambda *a: _anthropic_tool_use_response(tool_input={"city": "Paris"}, text="Let me check."),
    )

    response = provider.complete_with_tools(
        [{"role": "user", "content": "weather?"}], system_prompt="sys", tools=_TOOLS, max_tokens=10, timeout_seconds=5
    )

    assert response.text == "Let me check."
    assert len(response.tool_uses) == 1


def test_anthropic_complete_with_tools_sends_tool_definitions_and_message_history():
    captured = {}

    def fake_request_fn(api_key, payload, timeout_seconds):
        captured["payload"] = payload
        return _anthropic_response("ok")

    provider = AnthropicProvider(api_key="key", model="m", request_fn=fake_request_fn)
    messages = [{"role": "user", "content": "weather?"}, {"role": "assistant", "content": "checking"}]

    provider.complete_with_tools(messages, system_prompt="sys", tools=_TOOLS, max_tokens=10, timeout_seconds=5)

    assert captured["payload"]["messages"] == messages
    assert captured["payload"]["tools"] == [
        {"name": "get_weather", "description": "Gets the weather", "input_schema": {"type": "object"}}
    ]
    assert captured["payload"]["system"] == "sys"


def test_anthropic_complete_with_tools_raises_response_error_on_missing_content():
    provider = AnthropicProvider(api_key="key", model="m", request_fn=lambda *a: {"model": "m"})

    with pytest.raises(AIProviderResponseError):
        provider.complete_with_tools([], system_prompt="sys", tools=_TOOLS, max_tokens=10, timeout_seconds=5)


# --- complete_with_tools_with_retries -----------------------------------


class _FlakyToolProvider(AIProvider):
    def __init__(self, error: Exception, fail_count: int):
        self._error = error
        self._fail_count = fail_count
        self.calls = 0

    def complete(self, request, *, timeout_seconds):
        raise NotImplementedError("not exercised by these tests")

    def complete_with_tools(self, messages, *, system_prompt, tools, max_tokens, timeout_seconds):
        self.calls += 1
        if self.calls <= self._fail_count:
            raise self._error
        return AIToolCompletionResponse(text="ok", tool_uses=[], model="m", input_tokens=1, output_tokens=1)


class _AlwaysFailsToolProvider(AIProvider):
    def __init__(self, error: Exception):
        self._error = error
        self.calls = 0

    def complete(self, request, *, timeout_seconds):
        raise NotImplementedError("not exercised by these tests")

    def complete_with_tools(self, messages, *, system_prompt, tools, max_tokens, timeout_seconds):
        self.calls += 1
        raise self._error


def test_complete_with_tools_with_retries_succeeds_after_transient_failures():
    provider = _FlakyToolProvider(AIProviderTimeoutError("slow"), fail_count=1)
    sleeps, sleep_fn = _sleep_recorder()

    response = complete_with_tools_with_retries(
        provider, [], system_prompt="s", tools=_TOOLS, max_tokens=10, max_retries=2, sleep_fn=sleep_fn
    )

    assert response.text == "ok"
    assert provider.calls == 2
    assert sleeps == [1.0]


def test_complete_with_tools_with_retries_raises_after_exhausting_retries():
    provider = _AlwaysFailsToolProvider(AIProviderRateLimitError("slow down"))
    _, sleep_fn = _sleep_recorder()

    with pytest.raises(AIProviderRateLimitError):
        complete_with_tools_with_retries(
            provider, [], system_prompt="s", tools=_TOOLS, max_tokens=10, max_retries=2, sleep_fn=sleep_fn
        )

    assert provider.calls == 3


def test_complete_with_tools_with_retries_never_retries_non_transient_errors():
    provider = _AlwaysFailsToolProvider(AIProviderAuthenticationError("bad key"))
    _, sleep_fn = _sleep_recorder()

    with pytest.raises(AIProviderAuthenticationError):
        complete_with_tools_with_retries(
            provider, [], system_prompt="s", tools=_TOOLS, max_tokens=10, max_retries=5, sleep_fn=sleep_fn
        )

    assert provider.calls == 1
