from unittest.mock import AsyncMock, MagicMock


def test_health_ok(client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    client.app.state.ollama_client._http.get = AsyncMock(return_value=mock_response)

    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["checks"]["available"] is True


def test_health_ollama_down(client):
    import httpx

    client.app.state.ollama_client._http.get = AsyncMock(
        side_effect=httpx.ConnectError("refused")
    )

    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["checks"]["available"] is False
