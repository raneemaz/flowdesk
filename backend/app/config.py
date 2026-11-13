"""Per-environment Flask configuration, selected by FLASK_ENV."""
import os

API_PREFIX = "/api/v1"


class Config:
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
    JSON_SORT_KEYS = False


class DevelopmentConfig(Config):
    DEBUG = True
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-not-for-production")


class TestingConfig(Config):
    TESTING = True
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "test-secret-key-not-for-production")


class ProductionConfig(Config):
    DEBUG = False


CONFIG_BY_NAME = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
