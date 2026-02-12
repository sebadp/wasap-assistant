import logging

import httpx

logger = logging.getLogger(__name__)

GRAPH_API_URL = "https://graph.facebook.com/v22.0"


class WhatsAppClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        access_token: str,
        phone_number_id: str,
    ):
        self._http = http_client
        self._access_token = access_token
        self._phone_number_id = phone_number_id

    @property
    def _base_url(self) -> str:
        return f"{GRAPH_API_URL}/{self._phone_number_id}"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _normalize_ar_number(number: str) -> str:
        """Convert Argentine mobile numbers from 549xxx to 54xxx format."""
        if number.startswith("549") and len(number) == 13:
            return "54" + number[3:]
        return number

    def _check_auth_error(self, resp: httpx.Response) -> None:
        if resp.status_code == 401:
            logger.error(
                "WhatsApp API auth failed (401) — access token expired or invalid. "
                "Renew it at https://developers.facebook.com → WhatsApp → API Setup"
            )
        elif resp.status_code == 400 and "permission" in resp.text.lower():
            logger.error(
                "WhatsApp API permission error (400) — the access token lacks required permissions. "
                "Check that your System User has 'whatsapp_business_messaging' permission "
                "in Meta Business Suite → System Users"
            )
        resp.raise_for_status()

    async def send_message(self, to: str, text: str) -> None:
        to = self._normalize_ar_number(to)
        url = f"{self._base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        resp = await self._http.post(url, json=payload, headers=self._headers)
        if resp.status_code != 200:
            logger.error("Send failed [%s] %s: %s", to, resp.status_code, resp.text)
        self._check_auth_error(resp)
        logger.info("Outgoing  [%s]: %s", to, text[:80])

    async def mark_as_read(self, message_id: str) -> None:
        url = f"{self._base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        resp = await self._http.post(url, json=payload, headers=self._headers)
        self._check_auth_error(resp)
