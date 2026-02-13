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

    async def chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        url = f"{self._base_url}/api/chat"
        use_model = model or self._model

        msg_dicts = []
        for m in messages:
            d = {"role": m.role, "content": m.content}
            if m.images:
                d["images"] = m.images
            msg_dicts.append(d)

        payload = {
            "model": use_model,
            "messages": msg_dicts,
            "stream": False,
        }
        # Only enable thinking for the default chat model (qwen3 supports it, llava doesn't)
        if model is None:
            payload["think"] = True
        resp = await self._http.post(url, json=payload)
        if resp.status_code == 404:
            logger.error(
                "Ollama model '%s' not found — download it with: "
                "docker compose exec ollama ollama pull %s",
                use_model,
                use_model,
            )
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
