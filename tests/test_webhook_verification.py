from tests.conftest import TEST_SETTINGS


def test_verify_webhook_success(client):
    resp = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": TEST_SETTINGS.whatsapp_verify_token,
            "hub.challenge": "challenge_code_123",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "challenge_code_123"


def test_verify_webhook_wrong_token(client):
    resp = client.get(
        "/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong_token",
            "hub.challenge": "challenge_code_123",
        },
    )
    assert resp.status_code == 403


def test_verify_webhook_wrong_mode(client):
    resp = client.get(
        "/webhook",
        params={
            "hub.mode": "unsubscribe",
            "hub.verify_token": TEST_SETTINGS.whatsapp_verify_token,
            "hub.challenge": "challenge_code_123",
        },
    )
    assert resp.status_code == 403


def test_verify_webhook_missing_params(client):
    resp = client.get("/webhook")
    assert resp.status_code == 403
