"""Central error handling.

Every error response uses the same envelope, regardless of source:

    {"success": false, "error": {"code": "...", "message": "...", "details": {...}}}

Route/service code in later tasks should raise APIError for expected,
user-facing failures (validation, conflict, etc.) instead of building
JSON responses by hand.
"""
from flask import jsonify
from werkzeug.exceptions import HTTPException

_HTTP_STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "UNPROCESSABLE_ENTITY",
    500: "INTERNAL_SERVER_ERROR",
}


class APIError(Exception):
    """Raised by route/service code for an expected, user-facing error."""

    def __init__(self, message, status_code=400, code=None, details=None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code or _HTTP_STATUS_CODES.get(status_code, "ERROR")
        self.details = details or {}


def _error_response(code, message, details, status_code):
    body = {"success": False, "error": {"code": code, "message": message, "details": details}}
    return jsonify(body), status_code


def register_error_handlers(app):
    @app.errorhandler(APIError)
    def handle_api_error(err):
        return _error_response(err.code, err.message, err.details, err.status_code)

    @app.errorhandler(HTTPException)
    def handle_http_exception(err):
        code = _HTTP_STATUS_CODES.get(err.code, "HTTP_ERROR")
        message = err.description or err.name
        return _error_response(code, message, {}, err.code)

    @app.errorhandler(Exception)
    def handle_unexpected_exception(err):
        app.logger.exception("Unhandled exception")
        return _error_response(
            "INTERNAL_SERVER_ERROR",
            "An unexpected error occurred.",
            {},
            500,
        )
