def test_health_returns_200_and_ok_status(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
    assert body["data"]["database"] == "ok"
