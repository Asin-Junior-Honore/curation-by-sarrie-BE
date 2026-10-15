import httpx
from typing import List, Dict, Any
from ..config import settings


class BumpaClient:
    def __init__(self):
        self.base_url = settings.bumpa_base_url
        self.headers = {
            "X-Api-Key": settings.bumpa_api_key,
            "Accept": "application/json",
        }

    async def get_products(self, limit: int = 50, page: int = 1) -> Dict[str, Any]:
        """Fetch a page of products from Bumpa."""
        url = f"{self.base_url}/products"
        params = {"limit": limit, "page": page}

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()

    async def get_all_products(self) -> List[Dict[str, Any]]:
        """Fetch ALL products across all pages."""
        all_products = []
        page = 1
        per_page = 50

        while True:
            data = await self.get_products(limit=per_page, page=page)
            products = data.get("data", [])
            if not products:
                break
            all_products.extend(products)

            if not data.get("next_page_url"):
                break
            page += 1

        return all_products

    async def get_product_by_id(self, product_id: int) -> Dict[str, Any]:
        """Fetch a single product."""
        url = f"{self.base_url}/products/{product_id}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()


bumpa_client = BumpaClient()