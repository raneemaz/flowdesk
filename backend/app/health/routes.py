from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
def get_health():
    body = {"success": True, "message": "FlowDesk API is healthy", "data": {"status": "ok"}}
    return jsonify(body), 200
