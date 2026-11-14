"""Per-environment Flask configuration, selected by FLASK_ENV.

Config values are read inside __init__, not as class attributes, and
load_dotenv() runs before any of that - so .env is always picked up
regardless of import order, and tests that monkeypatch os.environ before
calling create_app() see their changes take effect.
"""
import os
from datetime import timedelta

import redis
from dotenv import load_dotenv

load_dotenv()

API_PREFIX = "/api/v1"


def _engine_options():
    return {
        "pool_pre_ping": True,
        "pool_size": int(os.environ.get("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        "pool_recycle": 1800,
    }


class Config:
    JSON_SORT_KEYS = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    def __init__(self):
        self.DEBUG = False
        self.TESTING = False
        self.SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
        self.SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
        self.SQLALCHEMY_ENGINE_OPTIONS = _engine_options()

        # Server-side sessions (Redis), per Section 35 open decision #3.
        # redis.from_url() is lazy - it does not connect until first used,
        # so this is safe even when Redis isn't reachable yet.
        self.SESSION_TYPE = "redis"
        self.SESSION_REDIS = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
        self.SESSION_PERMANENT = True
        self.PERMANENT_SESSION_LIFETIME = timedelta(days=int(os.environ.get("SESSION_LIFETIME_DAYS", "7")))
        # SESSION_USE_SIGNER is deliberately omitted: Flask-Session 0.8.0
        # deprecated it (no documented replacement yet, slated for
        # near-term removal). The session ID itself is already a long
        # cryptographically random value; HttpOnly/Secure/SameSite below
        # remain the primary cookie protections regardless.
        self.SESSION_KEY_PREFIX = "flowdesk:session:"
        self.SESSION_COOKIE_HTTPONLY = True
        self.SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
        # Default false for local (non-HTTPS) dev; ProductionConfig flips
        # the default to true per NFR-002 (all production traffic is HTTPS).
        self.SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"

        # Invitation email delivery (FD-016), per Section 35 open
        # decision #4: SMTP rather than a vendor SDK, so dev and
        # production run the exact same code path (app/email/client.py)
        # - only these env vars change between them. SMTP_HOST empty is
        # the dev-only "log instead of send" fallback; ProductionConfig
        # requires it to be set (checked at startup in app/__init__.py).
        self.SMTP_HOST = os.environ.get("SMTP_HOST", "")
        self.SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
        self.SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
        self.SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
        self.SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"
        self.EMAIL_FROM_ADDRESS = os.environ.get("EMAIL_FROM_ADDRESS", "no-reply@flowdesk.local")
        # Reuses FRONTEND_ORIGIN (already defined for CORS) to build the
        # link inside an invitation email, rather than adding a second,
        # near-duplicate "where's the frontend" env var. The frontend
        # route itself doesn't exist yet (FD-017+).
        self.FRONTEND_URL = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")
        self.INVITATION_EXPIRY_DAYS = int(os.environ.get("INVITATION_EXPIRY_DAYS", "7"))


class DevelopmentConfig(Config):
    def __init__(self):
        super().__init__()
        self.DEBUG = True
        self.SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-not-for-production")


class TestingConfig(Config):
    def __init__(self):
        super().__init__()
        self.TESTING = True
        self.SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "test-secret-key-not-for-production")
        self.SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", os.environ.get("DATABASE_URL"))

        # No Redis in this dev environment (same gap as Docker in FD-006) -
        # fakeredis stands in so tests still exercise the real Flask-Session
        # Redis code path. Dev/production always use genuine Redis above.
        # fakeredis is dev/test-only (requirements-dev.txt); importing it
        # lazily here keeps it off the production dependency list.
        import fakeredis

        self.SESSION_REDIS = fakeredis.FakeStrictRedis()

        # Force the dev-log fallback regardless of a real SMTP_HOST in
        # .env (set for local development use) - tests must never
        # attempt a real network send. app.email.client.send_email logs
        # instead of connecting when SMTP_HOST is empty.
        self.SMTP_HOST = ""


class ProductionConfig(Config):
    def __init__(self):
        super().__init__()
        self.DEBUG = False
        self.SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() == "true"


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
