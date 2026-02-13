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
    # Argentine number normalization: 549 → 54
    assert payload["to"] == "541112345678"
    assert payload["text"]["body"] == "Hello!"


@pytest.mark.asyncio
async def test_mark_as_read(wa_client):
    await wa_client.mark_as_read("wamid.test123")
    wa_client._http.post.assert_called_once()
    call_kwargs = wa_client._http.post.call_args
    payload = call_kwargs.kwargs["json"]
    assert payload["status"] == "read"
    assert payload["message_id"] == "wamid.test123"


@pytest.mark.asyncio
async def test_download_media():
    mock_http = AsyncMock()

    # First call: metadata response with URL
    meta_response = MagicMock()
    meta_response.raise_for_status = MagicMock()
    meta_response.json.return_value = {"url": "https://media.example.com/file.ogg"}

    # Second call: binary download
    binary_response = MagicMock()
    binary_response.raise_for_status = MagicMock()
    binary_response.content = b"audio-binary-data"

    mock_http.get = AsyncMock(side_effect=[meta_response, binary_response])

    client = WhatsAppClient(
        http_client=mock_http,
        access_token="test_token",
        phone_number_id="123456",
    )
    data = await client.download_media("media123")
    assert data == b"audio-binary-data"
    assert mock_http.get.call_count == 2


@pytest.mark.asyncio
async def test_send_reaction(wa_client):
    await wa_client.send_reaction("wamid.test123", "5491112345678", "\u23f3")
    wa_client._http.post.assert_called_once()
    call_kwargs = wa_client._http.post.call_args
    payload = call_kwargs.kwargs["json"]
    assert payload["type"] == "reaction"
    assert payload["reaction"]["message_id"] == "wamid.test123"
    assert payload["reaction"]["emoji"] == "\u23f3"
