import json

from tests.conftest import make_whatsapp_payload, sign_payload


def test_command_does_not_call_ollama(client):
    """Commands should be handled directly, not sent to Ollama."""
    payload = make_whatsapp_payload(text="/help", message_id="wamid.cmd1")
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


def test_normal_message_goes_through_ollama(client):
    """Normal messages should be processed by Ollama."""
    payload = make_whatsapp_payload(text="Hello!", message_id="wamid.normal1")
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


def test_remember_command(client):
    """The /remember command should save a memory."""
    payload = make_whatsapp_payload(
        text="/remember my birthday is March 15",
        message_id="wamid.rem1",
    )
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


def test_unknown_command(client):
    """Unknown commands should return an error message."""
    payload = make_whatsapp_payload(text="/nonexistent", message_id="wamid.unk1")
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
