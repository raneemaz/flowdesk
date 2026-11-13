"""Per-environment Flask configuration, selected by FLASK_ENV.

Config values are read inside __init__, not as class attributes, and
load_dotenv() runs before any of that - so .env is always picked up
regardless of import order, and tests that monkeypatch os.environ before
calling create_app() see their changes take effect.
"""
import os

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


class ProductionConfig(Config):
    def __init__(self):
        super().__init__()
        self.DEBUG = False


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
