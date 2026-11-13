"""Central error handling.

Every error response uses the same envelope, regardless of source:

    {"success": false, "error": {"code": "...", "message": "...", "details": {...}}}

Route/service code in later tasks should raise APIError for expected,
user-facing failures (validation, conflict, etc.) instead of building
JSON responses by hand.
"""
import json

from flask import jsonify
from werkzeug.exceptions import HTTPException
from werkzeug.wrappers import Response as WerkzeugResponse

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


def validation_error_details(exc) -> dict:
    """Converts a pydantic ValidationError into our error envelope's
    `details` shape. Shared across every route that validates a request
    body with a pydantic schema."""
    details = {}
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "body"
        details[field] = error["msg"]
    return details


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

    _install_wsgi_safety_net(app)


def _install_wsgi_safety_net(app):
    """@app.errorhandler only covers Flask's view-dispatch phase. An
    exception raised afterward, during response finalization (e.g.
    Flask-Session failing to write to Redis after the view already
    returned successfully), propagates past it entirely and would
    otherwise reach the client as Werkzeug's raw default error page
    instead of our envelope - violating NFR-007. This wraps the WSGI app
    itself as a last-resort catch-all."""
    flask_wsgi_app = app.wsgi_app

    def wsgi_app_with_safety_net(environ, start_response):
        try:
            return flask_wsgi_app(environ, start_response)
        except Exception:
            app.logger.exception("Unhandled exception escaped Flask's own error handling")
            body = {
                "success": False,
                "error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred.", "details": {}},
            }
            response = WerkzeugResponse(json.dumps(body), status=500, mimetype="application/json")
            return response(environ, start_response)

    app.wsgi_app = wsgi_app_with_safety_net
