from app.webhook.parser import extract_messages
from tests.conftest import make_whatsapp_payload


def test_extract_text_message():
    payload = make_whatsapp_payload(text="Hola mundo")
    messages = extract_messages(payload)
    assert len(messages) == 1
    assert messages[0].text == "Hola mundo"
    assert messages[0].from_number == "5491112345678"
    assert messages[0].type == "text"


def test_extract_empty_payload():
    messages = extract_messages({"object": "whatsapp_business_account", "entry": []})
    assert messages == []


def test_extract_status_update():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "BIZ_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "1234567890",
                                "phone_number_id": "123456",
                            },
                            "statuses": [
                                {
                                    "id": "wamid.xxx",
                                    "status": "delivered",
                                    "timestamp": "1700000000",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    messages = extract_messages(payload)
    assert messages == []


def test_extract_unsupported_type_ignored():
    """Unsupported types like sticker should be filtered out."""
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "BIZ_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "1234567890",
                                "phone_number_id": "123456",
                            },
                            "messages": [
                                {
                                    "from": "5491112345678",
                                    "id": "wamid.stk1",
                                    "timestamp": "1700000000",
                                    "type": "sticker",
                                    "sticker": {"id": "stk123"},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    messages = extract_messages(payload)
    assert messages == []


def test_extract_audio_message():
    payload = make_whatsapp_payload(msg_type="audio", media_id="aud123")
    messages = extract_messages(payload)
    assert len(messages) == 1
    assert messages[0].type == "audio"
    assert messages[0].media_id == "aud123"
    assert messages[0].text == ""


def test_extract_image_message():
    payload = make_whatsapp_payload(msg_type="image", media_id="img123")
    messages = extract_messages(payload)
    assert len(messages) == 1
    assert messages[0].type == "image"
    assert messages[0].media_id == "img123"
    assert messages[0].text == ""


def test_extract_image_with_caption():
    payload = make_whatsapp_payload(msg_type="image", media_id="img123", caption="Look at this")
    messages = extract_messages(payload)
    assert len(messages) == 1
    assert messages[0].type == "image"
    assert messages[0].text == "Look at this"
    assert messages[0].media_id == "img123"
