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
