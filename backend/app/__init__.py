"""Flask application factory."""
import os

from flask import Flask

from app.activity.routes import activity_bp
from app.ai_assistant.routes import ai_assistant_bp
from app.ai_reports.routes import ai_reports_bp
from app.analytics.routes import analytics_bp
from app.auth.routes import auth_bp
from app.config import API_PREFIX, CONFIG_BY_NAME
from app.customer_requests.routes import customer_requests_bp
from app.customers.routes import customers_bp
from app.departments.routes import departments_bp
from app.docs.routes import build_swagger_ui_blueprint, docs_bp
from app.employees.routes import employees_bp
from app.errors import register_error_handlers
from app.extensions import cors, db, limiter, migrate, sess
from app.health.routes import health_bp
from app.invitations.routes import invitations_bp
from app.invoices.routes import invoices_bp
from app.notifications.routes import notifications_bp
from app.organizations.routes import organizations_bp
from app.payments.routes import payments_bp
from app.tasks.routes import tasks_bp

# Importing app.models registers every model's table on db.metadata, so
# Alembic autogenerate and db.create_all() both see them. Required even
# though nothing here references the names directly.
from app import models  # noqa: F401


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
    if config_name == "production" and not app.config["SMTP_HOST"]:
        raise RuntimeError("SMTP_HOST must be set in the environment for production (invitation emails).")
    # FD-064: unlike ANTHROPIC_API_KEY (an optional feature that fails
    # gracefully per-request when unset), sessions and rate limiting
    # are required for the app to function at all - REDIS_URL silently
    # defaulting to localhost:6379 (app/config.py) would otherwise fail
    # confusingly at first login/request in production rather than at
    # startup, the same "fail fast with a clear message" the three
    # checks above already give SECRET_KEY/DATABASE_URL/SMTP_HOST.
    if config_name == "production" and not os.environ.get("REDIS_URL"):
        raise RuntimeError("REDIS_URL must be set in the environment for production (sessions, rate limiting).")
    # FD-065: the dev default (localhost:5173) would otherwise silently
    # become production's own CORS allow-list, blocking the real
    # frontend origin entirely rather than failing at startup with a
    # clear message.
    if config_name == "production" and not os.environ.get("FRONTEND_ORIGIN"):
        raise RuntimeError("FRONTEND_ORIGIN must be set in the environment for production (CORS).")

    db.init_app(app)
    migrate.init_app(app, db)
    sess.init_app(app)
    limiter.init_app(app)
    cors.init_app(
        app,
        resources={f"{API_PREFIX}/*": {"origins": app.config["FRONTEND_URL"]}},
        supports_credentials=True,
        allow_headers=["Content-Type", "X-CSRF-Token"],
        methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    )

    register_error_handlers(app)
    register_blueprints(app)

    return app


def register_blueprints(app):
    app.register_blueprint(auth_bp, url_prefix=API_PREFIX)
    app.register_blueprint(organizations_bp, url_prefix=API_PREFIX)
    app.register_blueprint(invitations_bp, url_prefix=API_PREFIX)
    app.register_blueprint(departments_bp, url_prefix=API_PREFIX)
    app.register_blueprint(employees_bp, url_prefix=API_PREFIX)
    app.register_blueprint(tasks_bp, url_prefix=API_PREFIX)
    app.register_blueprint(customers_bp, url_prefix=API_PREFIX)
    app.register_blueprint(customer_requests_bp, url_prefix=API_PREFIX)
    app.register_blueprint(invoices_bp, url_prefix=API_PREFIX)
    app.register_blueprint(payments_bp, url_prefix=API_PREFIX)
    app.register_blueprint(activity_bp, url_prefix=API_PREFIX)
    app.register_blueprint(analytics_bp, url_prefix=API_PREFIX)
    app.register_blueprint(ai_reports_bp, url_prefix=API_PREFIX)
    app.register_blueprint(ai_assistant_bp, url_prefix=API_PREFIX)
    app.register_blueprint(notifications_bp, url_prefix=API_PREFIX)
    app.register_blueprint(health_bp, url_prefix=API_PREFIX)
    app.register_blueprint(docs_bp, url_prefix=API_PREFIX)
    app.register_blueprint(build_swagger_ui_blueprint())
