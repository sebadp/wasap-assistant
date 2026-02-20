import json

from tests.conftest import make_whatsapp_payload, sign_payload


def test_incoming_webhook_valid(client):
    payload = make_whatsapp_payload()
    body = json.dumps(payload).encode()
    signature = sign_payload(body)

    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )
    assert resp.status_code == 200


def test_incoming_webhook_invalid_signature(client):
    payload = make_whatsapp_payload()
    body = json.dumps(payload).encode()

    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": "sha256=invalid",
        },
    )
    # Always returns 200 (Meta requirement)
    assert resp.status_code == 200


def test_incoming_webhook_non_whitelisted_number(client):
    payload = make_whatsapp_payload(from_number="9999999999")
    body = json.dumps(payload).encode()
    signature = sign_payload(body)

    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )
    assert resp.status_code == 200


def test_incoming_webhook_status_update(client):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "BIZ_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "statuses": [{"id": "wamid.xxx", "status": "delivered"}],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    body = json.dumps(payload).encode()
    signature = sign_payload(body)

    resp = client.post(
        "/webhook",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": signature,
        },
    )
    assert resp.status_code == 200
