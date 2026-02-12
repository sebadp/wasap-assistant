from unittest.mock import AsyncMock, MagicMock

import pytest

from app.whatsapp.client import WhatsAppClient


@pytest.fixture
def wa_client() -> WhatsAppClient:
    mock_http = AsyncMock()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_http.post = AsyncMock(return_value=mock_response)
    return WhatsAppClient(
        http_client=mock_http,
        access_token="test_token",
        phone_number_id="123456",
    )


@pytest.mark.asyncio
async def test_send_message(wa_client):
    await wa_client.send_message("5491112345678", "Hello!")
    wa_client._http.post.assert_called_once()
    call_kwargs = wa_client._http.post.call_args
    assert "messages" in call_kwargs.args[0]
    payload = call_kwargs.kwargs["json"]
    assert payload["to"] == "5491112345678"
    assert payload["text"]["body"] == "Hello!"


@pytest.mark.asyncio
async def test_mark_as_read(wa_client):
    await wa_client.mark_as_read("wamid.test123")
    wa_client._http.post.assert_called_once()
    call_kwargs = wa_client._http.post.call_args
    payload = call_kwargs.kwargs["json"]
    assert payload["status"] == "read"
    assert payload["message_id"] == "wamid.test123"
