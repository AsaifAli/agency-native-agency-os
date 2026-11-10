import httpx

class EvaluationClient:
    def __init__(self, base_url: str, api_token: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token

    async def evaluate(self, payload: dict) -> dict:
        headers = {"Authorization": f"Bearer {self.api_token}"} if self.api_token else {}
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(f"{self.base_url}/v1/evaluations", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()
