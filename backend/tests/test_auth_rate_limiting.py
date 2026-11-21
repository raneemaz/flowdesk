"""FD-064 (Section 13's "auth rate limiting" item). Rate limiting is
OFF by default for the whole test suite (app/config.py's TestingConfig
reads RATELIMIT_ENABLED from os.environ, defaulting to "false") -
every other test in this suite hits /auth/login and /auth/register
repeatedly and must never see a 429 it isn't testing for.

Flask-Limiter reads RATELIMIT_ENABLED exactly once, inside
`limiter.init_app(app)` (called from create_app()) - when disabled, it
skips its own storage/hook setup entirely, so flipping
`app.config["RATELIMIT_ENABLED"]` on an already-created app (the
standard `app`/`client` fixtures from conftest.py) has no effect.
These tests instead set the environment variable via `monkeypatch`
BEFORE calling `create_app("testing")` themselves, so the freshly
created app's own TestingConfig picks it up before `limiter.init_app`
runs."""
from app import create_app
from app.extensions import db
from app.models import User


def _rate_limited_client(monkeypatch):
    monkeypatch.setenv("RATELIMIT_ENABLED", "true")
    app = create_app("testing")
    return app, app.test_client()


def _clean_users(app):
    with app.app_context():
        db.session.query(User).delete()
        db.session.commit()


def test_login_is_rate_limited_per_ip(monkeypatch):
    app, client = _rate_limited_client(monkeypatch)
    client.post(
        "/api/v1/auth/register",
        json={"name": "Ada Lovelace", "email": "ada-ratelimit@example.com", "password": "correct horse battery"},
    )

    for _ in range(10):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "ada-ratelimit@example.com", "password": "wrong password"},
        )
        assert response.status_code == 401

    throttled = client.post(
        "/api/v1/auth/login",
        json={"email": "ada-ratelimit@example.com", "password": "wrong password"},
    )

    assert throttled.status_code == 429
    body = throttled.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "TOO_MANY_REQUESTS"
    _clean_users(app)


def test_register_is_rate_limited_per_ip(monkeypatch):
    app, client = _rate_limited_client(monkeypatch)

    for i in range(5):
        response = client.post(
            "/api/v1/auth/register",
            json={"name": "Spammer", "email": f"spam-{i}@example.com", "password": "correct horse battery"},
        )
        assert response.status_code == 201

    throttled = client.post(
        "/api/v1/auth/register",
        json={"name": "Spammer", "email": "spam-6@example.com", "password": "correct horse battery"},
    )

    assert throttled.status_code == 429
    assert throttled.get_json()["error"]["code"] == "TOO_MANY_REQUESTS"
    _clean_users(app)


def test_login_rate_limit_does_not_apply_across_different_ips(monkeypatch):
    app, client = _rate_limited_client(monkeypatch)
    client.post(
        "/api/v1/auth/register",
        json={"name": "Ada Lovelace", "email": "ada-multi-ip@example.com", "password": "correct horse battery"},
    )

    for _ in range(10):
        client.post(
            "/api/v1/auth/login",
            json={"email": "ada-multi-ip@example.com", "password": "wrong password"},
            environ_overrides={"REMOTE_ADDR": "203.0.113.1"},
        )

    response_from_a_different_ip = client.post(
        "/api/v1/auth/login",
        json={"email": "ada-multi-ip@example.com", "password": "wrong password"},
        environ_overrides={"REMOTE_ADDR": "203.0.113.2"},
    )

    assert response_from_a_different_ip.status_code == 401  # not 429 - a different caller, not throttled
    _clean_users(app)
