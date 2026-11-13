"""Flask application factory."""
import os

from flask import Flask

from app.config import API_PREFIX, CONFIG_BY_NAME
from app.errors import register_error_handlers
from app.extensions import db
from app.health.routes import health_bp


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    if config_name not in CONFIG_BY_NAME:
        raise ValueError(f"Unknown FLASK_ENV '{config_name}'. Expected one of: {', '.join(CONFIG_BY_NAME)}")

    app = Flask(__name__)
    app.config.from_object(CONFIG_BY_NAME[config_name]())
    app.config["ENV_NAME"] = config_name

    if config_name == "production" and not app.config["SECRET_KEY"]:
        raise RuntimeError("FLASK_SECRET_KEY must be set in the environment for production.")
    if config_name == "production" and not app.config["SQLALCHEMY_DATABASE_URI"]:
        raise RuntimeError("DATABASE_URL must be set in the environment for production.")

    db.init_app(app)

    register_error_handlers(app)
    register_blueprints(app)

    return app


def register_blueprints(app):
    app.register_blueprint(health_bp, url_prefix=API_PREFIX)
