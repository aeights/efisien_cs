import httpx


class WahaClient:
    """Minimal client for the WAHA WhatsApp HTTP API."""

    def __init__(self, *, base_url: str, session: str, api_key: str, client=None) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = session
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=30)

    def send_text(self, chat_id: str, text: str) -> None:
        resp = self._client.post(
            f"{self._base_url}/api/sendText",
            json={"session": self._session, "chatId": chat_id, "text": text},
            headers={"X-Api-Key": self._api_key},
        )
        resp.raise_for_status()
