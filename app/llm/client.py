import logging

import httpx

from app.models import ChatMessage

logger = logging.getLogger(__name__)


class OllamaClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        base_url: str,
        model: str,
    ):
        self._http = http_client
        self._base_url = base_url.rstrip("/")
        self._model = model

    async def chat(self, messages: list[ChatMessage]) -> str:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": [m.model_dump() for m in messages],
            "stream": False,
            "think": True,
        }
        resp = await self._http.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data["message"]["content"]
        logger.debug("LLM raw response: %s", content[:500])
        return content

    async def is_available(self) -> bool:
        try:
            resp = await self._http.get(
                f"{self._base_url}/api/tags",
                timeout=5.0,
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
