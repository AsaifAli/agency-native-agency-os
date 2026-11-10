import httpx

class N8nClient:
    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    async def trigger(self, webhook_path: str, payload: dict) -> dict:
        headers = {"X-N8N-API-KEY": self.api_key} if self.api_key else {}
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(f"{self.base_url}/webhook/{webhook_path.lstrip('/')}",
                                         json=payload, headers=headers)
            response.raise_for_status()
            return response.json() if response.content else {"accepted": True}
