from flask import Blueprint, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def get_health():
    """Liveness check. Always 200 if the app process can respond; the
    'database' field reports connectivity without coupling liveness to it
    (a readiness probe, not this endpoint, should gate on that)."""
    try:
        db.session.execute(text("SELECT 1"))
        database_status = "ok"
    except SQLAlchemyError:
        database_status = "unavailable"

    body = {
        "success": True,
        "message": "FlowDesk API is healthy",
        "data": {"status": "ok", "database": database_status},
    }
    return jsonify(body), 200
