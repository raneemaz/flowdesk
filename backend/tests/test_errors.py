def test_unknown_route_returns_hybrid_404_envelope(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    body = response.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"
    assert "message" in body["error"]
    assert "details" in body["error"]


def test_wrong_method_returns_hybrid_405_envelope(client):
    response = client.post("/api/v1/health")

    assert response.status_code == 405
    body = response.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_exception_during_response_finalization_still_returns_hybrid_envelope(app, client):
    """@app.errorhandler only covers Flask's view-dispatch phase (FD-010
    found this the hard way: a session-save failure after the view
    already returned bypassed it entirely, leaking Werkzeug's raw default
    error page). This simulates that class of failure generically, via
    an after_request hook, to prove the WSGI-level safety net in
    app.errors.register_error_handlers actually catches it."""

    @app.after_request
    def _boom(response):
        raise RuntimeError("simulated failure during response finalization")

    try:
        response = client.get("/api/v1/health")
    finally:
        app.after_request_funcs[None].remove(_boom)

    assert response.status_code == 500
    assert response.content_type == "application/json"
    body = response.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "INTERNAL_SERVER_ERROR"
