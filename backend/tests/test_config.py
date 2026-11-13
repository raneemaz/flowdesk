import pytest

from app import create_app


def test_unknown_env_name_is_rejected():
    with pytest.raises(ValueError):
        create_app("not-a-real-environment")


def test_production_requires_secret_key(monkeypatch):
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError):
        create_app("production")


def test_development_config_has_debug_enabled():
    app = create_app("development")

    assert app.config["DEBUG"] is True


def test_testing_config_has_testing_enabled():
    app = create_app("testing")

    assert app.config["TESTING"] is True
