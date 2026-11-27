"""Cloudflare Turnstile gate on POST /auth/register and /auth/login."""

import os
import urllib.error

import pytest

from app.auth import turnstile
from app.extensions import db
from app.models import User

PASSWORD = "correct horse battery"
EMAIL = "bot-check@turnstile.example.com"


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        db.session.query(User).delete()
        db.session.commit()


@pytest.fixture
def enabled(app):
    app.config["TURNSTILE_SECRET"] = "server-secret"
    app.config["TURNSTILE_HOSTNAMES"] = "flowdesk.example.com"
    return app


def _verify_returns(monkeypatch, result):
    calls = []

    def fake(secret, token, remote_ip):
        calls.append({"secret": secret, "token": token, "remote_ip": remote_ip})
        return result

    monkeypatch.setattr(turnstile, "_siteverify", fake)
    return calls


def _register(client, **extra):
    return client.post("/api/v1/auth/register", json={"name": "Ada", "email": EMAIL, "password": PASSWORD, **extra})


def test_check_is_off_when_no_secret_is_configured(client, monkeypatch):
    calls = _verify_returns(monkeypatch, {"success": False})

    assert _register(client).status_code == 201
    assert calls == []


def test_register_requires_a_token_when_enabled(enabled, client, app):
    response = _register(client)

    assert response.status_code == 403
    assert response.get_json()["error"]["code"] == "BOT_CHECK_FAILED"
    with app.app_context():
        assert db.session.query(User).filter_by(email=EMAIL).count() == 0


def test_register_passes_with_a_verified_token(enabled, client, monkeypatch):
    calls = _verify_returns(monkeypatch, {"success": True, "action": "signup", "hostname": "flowdesk.example.com"})

    response = _register(client, turnstile_token="tok-123")

    assert response.status_code == 201
    assert calls[0]["secret"] == "server-secret"
    assert calls[0]["token"] == "tok-123"


@pytest.mark.parametrize(
    "result",
    [
        {"success": False, "error-codes": ["invalid-input-response"]},
        {"success": True, "action": "login", "hostname": "flowdesk.example.com"},  # token minted for another form
        {"success": True, "action": "signup", "hostname": "evil.example.com"},  # wrong site
        {"success": "true", "action": "signup", "hostname": "flowdesk.example.com"},  # not a real boolean
    ],
)
def test_register_rejects_unverified_tokens(enabled, client, monkeypatch, result, app):
    _verify_returns(monkeypatch, result)

    response = _register(client, turnstile_token="tok-123")

    assert response.status_code == 403
    with app.app_context():
        assert db.session.query(User).filter_by(email=EMAIL).count() == 0


def test_fails_closed_when_cloudflare_is_unreachable(enabled, client, monkeypatch):
    def down(secret, token, remote_ip):
        raise urllib.error.URLError("unreachable")

    monkeypatch.setattr(turnstile, "_siteverify", down)

    assert _register(client, turnstile_token="tok-123").status_code == 403


def test_oversized_token_is_rejected_without_calling_cloudflare(enabled, client, monkeypatch):
    calls = _verify_returns(monkeypatch, {"success": True, "action": "signup", "hostname": "flowdesk.example.com"})

    assert _register(client, turnstile_token="x" * 3000).status_code == 403
    assert calls == []


def test_login_is_gated_with_its_own_action(enabled, client, monkeypatch, app):
    app.config["TURNSTILE_SECRET"] = ""
    _register(client)
    app.config["TURNSTILE_SECRET"] = "server-secret"

    _verify_returns(monkeypatch, {"success": True, "action": "signup", "hostname": "flowdesk.example.com"})
    wrong_action = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD, "turnstile_token": "t"})
    assert wrong_action.status_code == 403

    _verify_returns(monkeypatch, {"success": True, "action": "login", "hostname": "flowdesk.example.com"})
    ok = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD, "turnstile_token": "t"})
    assert ok.status_code == 200


def test_test_key_results_are_refused_in_production(enabled, client, monkeypatch, app):
    app.config["ENV_NAME"] = "production"
    _verify_returns(monkeypatch, {"success": True, "hostname": "flowdesk.example.com", "metadata": {"result_with_testing_key": True}})

    assert _register(client, turnstile_token="tok").status_code == 403


def test_non_object_json_body_is_not_a_server_error(enabled, client):
    response = client.post("/api/v1/auth/register", json=["not", "an", "object"])

    assert response.status_code == 403


@pytest.mark.skipif(os.environ.get("TURNSTILE_LIVE_TEST") != "1", reason="set TURNSTILE_LIVE_TEST=1 to call Cloudflare")
def test_live_siteverify_with_cloudflare_test_keys(client, app):
    # Cloudflare's published always-pass test secret; it answers with
    # hostname "example.com" and no action.
    app.config["TURNSTILE_SECRET"] = "1x0000000000000000000000000000000AA"
    app.config["TURNSTILE_HOSTNAMES"] = "example.com"

    assert _register(client, turnstile_token="XXXX.DUMMY.TOKEN.XXXX").status_code == 201

    app.config["TURNSTILE_SECRET"] = "2x0000000000000000000000000000000AA"  # always-fail test secret
    second = client.post(
        "/api/v1/auth/register",
        json={"name": "Bo", "email": "second@turnstile.example.com", "password": PASSWORD, "turnstile_token": "XXXX.DUMMY.TOKEN.XXXX"},
    )
    assert second.status_code == 403
