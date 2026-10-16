import httpx
from typing import Optional, Dict, Any
from ..config import settings


class PaystackClient:
    def __init__(self):
        self.base_url = settings.paystack_base_url
        self.secret_key = settings.paystack_secret_key
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    async def initialize_transaction(
        self,
        email: str,
        amount_kobo: int,
        reference: str,
        callback_url: str,
        metadata: Optional[Dict[str, Any]] = None,
        channels: Optional[list] = None,
    ) -> Dict[str, Any]:
        """
        Initialize a Paystack transaction.
        Returns the full response data including authorization_url.
        """
        payload = {
            "email": email,
            "amount": str(amount_kobo),  # Paystack expects string
            "reference": reference,
            "callback_url": callback_url,
            "currency": "NGN",
            "metadata": metadata or {},
        }
        if channels:
            payload["channels"] = channels

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.base_url}/transaction/initialize",
                headers=self.headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        if not data.get("status"):
            raise Exception(
                f"Paystack init failed: {data.get('message', 'Unknown error')}"
            )

        return data["data"]

    async def verify_transaction(self, reference: str) -> Dict[str, Any]:
        """Verify a transaction by reference."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{self.base_url}/transaction/verify/{reference}",
                headers=self.headers,
            )
            response.raise_for_status()
            data = response.json()

        if not data.get("status"):
            raise Exception(
                f"Paystack verify failed: {data.get('message', 'Unknown error')}"
            )

        return data["data"]


paystack_client = PaystackClient()