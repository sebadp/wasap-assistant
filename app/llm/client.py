from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.models import ChatMessage

logger = logging.getLogger(__name__)


@dataclass
class ChatResponse:
    content: str
    tool_calls: list[dict] | None = None


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

    def _build_message_dicts(self, messages: list[ChatMessage]) -> list[dict]:
        msg_dicts = []
        for m in messages:
            d: dict = {"role": m.role, "content": m.content}
            if m.images:
                d["images"] = m.images
            if m.tool_calls:
                d["tool_calls"] = m.tool_calls
            msg_dicts.append(d)
        return msg_dicts

    async def chat_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict] | None = None,
        model: str | None = None,
    ) -> ChatResponse:
        url = f"{self._base_url}/api/chat"
        use_model = model or self._model

        payload: dict = {
            "model": use_model,
            "messages": self._build_message_dicts(messages),
            "stream": False,
        }

        if tools:
            # think: True is incompatible with tools in qwen3
            payload["tools"] = tools
        elif model is None:
            # Only enable thinking for default chat model without tools
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
        msg = data["message"]
        content = msg.get("content", "")
        tool_calls = msg.get("tool_calls")
        logger.debug("LLM raw response: %s", content[:500] if content else "(tool_calls)")
        return ChatResponse(content=content, tool_calls=tool_calls)

    async def chat(self, messages: list[ChatMessage], model: str | None = None) -> str:
        response = await self.chat_with_tools(messages, tools=None, model=model)
        return response.content

    async def is_available(self) -> bool:
        try:
            resp = await self._http.get(
                f"{self._base_url}/api/tags",
                timeout=5.0,
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
