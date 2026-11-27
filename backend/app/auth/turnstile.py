"""Cloudflare Turnstile bot check for sign-up and login.

The browser solves the widget and sends its one-time token with the
form; this module redeems it at Cloudflare's siteverify endpoint before
the real handler runs. It fails closed: a missing token, a network
error, a non-2xx reply, an unexpected action or hostname all reject the
request.

Configuration (app/config.py):
- TURNSTILE_SECRET: the widget's secret. Empty = check disabled (local
  dev and tests), in which case the frontend shows no widget either.
- TURNSTILE_HOSTNAMES: comma-separated frontend hostnames the token must
  come from. A production value must never contain localhost.

Cloudflare's published test keys (always pass, hostname "example.com",
no action) are accepted only outside production.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

from flask import current_app, request

from app.errors import APIError

SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
_MAX_TOKEN_LENGTH = 2048
_TIMEOUT_SECONDS = 10


def _reject() -> APIError:
    return APIError(
        "The security check didn't pass. Please try again.",
        status_code=403,
        code="BOT_CHECK_FAILED",
    )


def _client_ip() -> str | None:
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.remote_addr


def _siteverify(secret: str, token: str, remote_ip: str | None) -> dict:
    fields = {"secret": secret, "response": token}
    if remote_ip:
        fields["remoteip"] = remote_ip
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(
        SITEVERIFY_URL, data=body, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode())


def require_turnstile(token: object, expected_action: str) -> None:
    """No-op when Turnstile isn't configured; otherwise raises a 403
    APIError unless Cloudflare confirms this exact token, action and
    hostname. Call before any of the handler's own work."""
    config = current_app.config
    secret = config.get("TURNSTILE_SECRET", "")
    if not secret:
        return

    hostnames = {h.strip() for h in config.get("TURNSTILE_HOSTNAMES", "").split(",") if h.strip()}
    if not isinstance(token, str) or not token or len(token) > _MAX_TOKEN_LENGTH or not hostnames:
        raise _reject()

    try:
        result = _siteverify(secret, token, _client_ip())
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        current_app.logger.warning("Turnstile siteverify unreachable or invalid response; rejecting.")
        raise _reject()

    is_test_key = bool((result.get("metadata") or {}).get("result_with_testing_key"))
    if is_test_key and config.get("ENV_NAME") == "production":
        raise _reject()
    action_ok = result.get("action") == expected_action or (is_test_key and not result.get("action"))
    if result.get("success") is not True or not action_ok or result.get("hostname") not in hostnames:
        raise _reject()
