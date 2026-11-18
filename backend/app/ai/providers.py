"""FD-055: the swappable AI-provider abstraction (spec Section 8's own
"Use a swappable LLM-provider abstraction so the project isn't locked
to one vendor"). `AIProvider` is the one interface every concrete
provider implements - deliberately generic (plain system/user prompt
text in, plain text out), not tied to the weekly-report shape, so a
future caller (e.g. FD-061's conversational assistant) can reuse it
for a different kind of exchange without this module ever changing.
`app.ai.service` is the one place that layers the weekly-report-
specific contract on top of this.

**`AnthropicProvider` is the one real implementation** - resolving
Section 35 open decision #12 ("AI provider, budget limits, privacy
terms, and model selection") as: Anthropic's Messages API, no hard
per-report budget cap beyond a bounded `max_tokens` + a request
timeout (enforced by `complete_with_retries` below), and - per
`app.ai.service`'s own contract - the provider never receives
anything but an already-computed metrics snapshot, never raw
database access or another organization's data.

**Plain stdlib `urllib`, not the official `anthropic` SDK** - same
reasoning `app.email.client`'s own module docstring gives for
choosing SMTP over a vendor SDK (one fewer dependency to install/
swap/mock), and this task was specifically asked to design the
timeout/retry rules itself (`complete_with_retries` below) rather
than delegate that to an SDK's own built-in retry behavior.

**Timeout/retry rules** (`complete_with_retries`): retries only the
genuinely transient failure modes - `AIProviderTimeoutError`,
`AIProviderRateLimitError`, `AIProviderUnavailableError` (the
provider's own infrastructure, 5xx or unreachable), and
`AIProviderResponseError` (a 2xx reply this module couldn't parse -
LLM output varies enough between calls that a second attempt may
produce something parseable). It never retries
`AIProviderAuthenticationError` (a bad/missing API key) or
`AIProviderRequestError` (this codebase's own malformed request) -
retrying either can never succeed.

Nothing in the running application calls `AnthropicProvider` yet
(FD-056 builds the metrics snapshot this exists to consume; FD-057
wires actual generation on top of `app.ai.service`) - so there is
deliberately no production-startup requirement for
`ANTHROPIC_API_KEY` yet, unlike `SMTP_HOST`'s own check in
`app/__init__.py`. That requirement belongs with whichever future
task first makes a real call load-bearing, not with this design-only
one."""

import abc
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

_ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_API_VERSION = "2023-06-01"


class AIProviderError(Exception):
    """Base class for every error this module raises."""


class AIProviderTimeoutError(AIProviderError):
    """Retryable - the request didn't complete within the configured timeout."""


class AIProviderRateLimitError(AIProviderError):
    """Retryable - the provider asked the caller to back off (HTTP 429)."""


class AIProviderUnavailableError(AIProviderError):
    """Retryable - the provider's own infrastructure failed (5xx) or was unreachable."""


class AIProviderAuthenticationError(AIProviderError):
    """Never retryable - a missing/invalid API key (HTTP 401/403)."""


class AIProviderRequestError(AIProviderError):
    """Never retryable - this codebase's own request was malformed (HTTP 400/422)."""


class AIProviderResponseError(AIProviderError):
    """Retryable - the provider responded 2xx but with content this
    module couldn't parse into the expected shape."""


# What complete_with_retries is willing to retry - see this module's
# own docstring for why each of these, and only these, is transient.
_RETRYABLE_ERRORS = (
    AIProviderTimeoutError,
    AIProviderRateLimitError,
    AIProviderUnavailableError,
    AIProviderResponseError,
)


@dataclass(frozen=True)
class AICompletionRequest:
    """Generic request shape - see the module docstring for why this
    is provider- and use-case-agnostic rather than weekly-report-
    specific."""

    system_prompt: str
    user_prompt: str
    max_tokens: int = 1024


@dataclass(frozen=True)
class AICompletionResponse:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


class AIProvider(abc.ABC):
    """Every concrete provider raises an `AIProviderError` subclass on
    any failure - never returns a partial/fabricated response, so a
    caller never mistakes a failed call for a successful one."""

    @abc.abstractmethod
    def complete(self, request: AICompletionRequest, *, timeout_seconds: float) -> AICompletionResponse:
        raise NotImplementedError


def _send_anthropic_request(api_key: str, payload: dict, timeout_seconds: float) -> dict:
    """The real HTTP call. Maps Anthropic's own HTTP status codes to
    this module's exception hierarchy once, here, so `AnthropicProvider
    .complete` never has to think about status codes - only about the
    (already-2xx) response shape. Injected as `request_fn` in
    `AnthropicProvider.__init__` so tests never perform a real network
    call - same dependency-injection convention
    `app.email.client.send_email`'s own `send_email_fn` parameter
    already established for SMTP."""
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        _ANTHROPIC_API_URL,
        data=data,
        method="POST",
        headers={
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_API_VERSION,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except TimeoutError as exc:
        raise AIProviderTimeoutError(f"Anthropic API request timed out: {exc}") from exc
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        if exc.code in (401, 403):
            raise AIProviderAuthenticationError(f"Anthropic API authentication failed: {error_body}") from exc
        if exc.code == 429:
            raise AIProviderRateLimitError(f"Anthropic API rate limit: {error_body}") from exc
        if exc.code >= 500:
            raise AIProviderUnavailableError(f"Anthropic API server error ({exc.code}): {error_body}") from exc
        raise AIProviderRequestError(f"Anthropic API rejected the request ({exc.code}): {error_body}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError) or "timed out" in str(exc.reason).lower():
            raise AIProviderTimeoutError(f"Anthropic API request timed out: {exc}") from exc
        raise AIProviderUnavailableError(f"Could not reach the Anthropic API: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise AIProviderResponseError(f"Anthropic API returned non-JSON content: {exc}") from exc


class AnthropicProvider(AIProvider):
    """The one real `AIProvider` this project implements (Section 35
    open decision #12). `request_fn` defaults to the real HTTP call
    above but is swappable for tests."""

    def __init__(self, *, api_key: str, model: str, request_fn=None):
        if not api_key:
            raise AIProviderAuthenticationError("An Anthropic API key is required.")
        self._api_key = api_key
        self._model = model
        self._request_fn = request_fn or _send_anthropic_request

    def complete(self, request: AICompletionRequest, *, timeout_seconds: float) -> AICompletionResponse:
        payload = {
            "model": self._model,
            "max_tokens": request.max_tokens,
            "system": request.system_prompt,
            "messages": [{"role": "user", "content": request.user_prompt}],
        }
        body = self._request_fn(self._api_key, payload, timeout_seconds)

        if not isinstance(body, dict):
            raise AIProviderResponseError("Anthropic API response was not a JSON object.")
        try:
            content_blocks = body["content"]
            text = "".join(block["text"] for block in content_blocks if block.get("type") == "text")
            usage = body.get("usage") or {}
            return AICompletionResponse(
                text=text,
                model=body.get("model", self._model),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )
        except (KeyError, TypeError) as exc:
            raise AIProviderResponseError(f"Unexpected Anthropic response shape: {exc}") from exc


def complete_with_retries(
    provider: AIProvider,
    request: AICompletionRequest,
    *,
    timeout_seconds: float = 30.0,
    max_retries: int = 2,
    backoff_seconds: float = 1.0,
    sleep_fn=time.sleep,
) -> AICompletionResponse:
    """FD-055's own "timeout/retry rules" - see the module docstring
    for exactly which errors are retried and why. Exponential backoff
    (`backoff_seconds * 2**attempt`); `sleep_fn` is injected so tests
    never actually sleep, same convention as `request_fn` above."""
    attempt = 0
    while True:
        try:
            return provider.complete(request, timeout_seconds=timeout_seconds)
        except _RETRYABLE_ERRORS:
            if attempt >= max_retries:
                raise
            sleep_fn(backoff_seconds * (2**attempt))
            attempt += 1


def build_default_provider() -> AnthropicProvider:
    """Reads `ANTHROPIC_API_KEY`/`ANTHROPIC_MODEL` from the current
    Flask app's config - the one place a future caller (FD-057+) gets
    a real, configured provider without hardcoding either value
    itself. `AnthropicProvider` itself stays framework-agnostic (no
    Flask import at class level) so it's just as testable outside a
    request/app context as any other provider would be."""
    from flask import current_app

    return AnthropicProvider(
        api_key=current_app.config["ANTHROPIC_API_KEY"], model=current_app.config["ANTHROPIC_MODEL"]
    )
