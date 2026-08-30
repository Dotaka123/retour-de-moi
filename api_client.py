import asyncio
import json
import os
import urllib.request
import urllib.error
from typing import Dict
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY", "")
BASE_URL = os.getenv("API_BASE_URL", "https://www.rakibsocials.com/api/v1")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}


class APIClient:
    """Client for interacting with the Logs API."""

    def __init__(self):
        self.base_url = BASE_URL
        self.headers = HEADERS
        # Product cache: {product_id: product_dict}
        self._product_cache = {}
        self._cache_time = 0
        self._cache_ttl = 300  # 5 minutes

    def _request_sync(self, method: str, endpoint: str, data: dict = None) -> Dict:
        """Make a synchronous API request using stdlib urllib."""
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(data).encode("utf-8") if data else None

        req = urllib.request.Request(url, data=body, headers=self.headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                return {"success": True, "data": result}
        except urllib.error.HTTPError as e:
            try:
                result = json.loads(e.read().decode("utf-8"))
            except Exception:
                result = {}
            return {
                "success": False,
                "error": result.get("error", f"http_{e.code}"),
                "detail": result.get("detail", f"HTTP error {e.code}")
            }
        except urllib.error.URLError as e:
            return {
                "success": False,
                "error": "connection_error",
                "detail": f"Failed to connect to API: {e.reason}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": "unexpected_error",
                "detail": str(e)
            }

    async def _request(self, method: str, endpoint: str, data: dict = None) -> Dict:
        """Make an async API request by running the sync version in a thread."""
        return await asyncio.to_thread(self._request_sync, method, endpoint, data)

    async def get_categories(self) -> Dict:
        """Get all product categories."""
        return await self._request("GET", "/categories")

    async def get_products(self, category_id: int = None,
                           in_stock: bool = None, page: int = 1) -> Dict:
        """Get products with optional filters."""
        params = []
        if category_id:
            params.append(f"category={category_id}")
        if in_stock is not None:
            params.append(f"in_stock={'true' if in_stock else 'false'}")
        if page > 1:
            params.append(f"page={page}")

        query = f"?{'&'.join(params)}" if params else ""
        return await self._request("GET", f"/products{query}")

    async def buy_product(self, product_id: int, quantity: int = 1) -> Dict:
        """Buy a product."""
        return await self._request("POST", "/buy", {
            "product": product_id,
            "quantity": quantity
        })

    async def get_balance(self) -> Dict:
        """Get API wallet balance."""
        return await self._request("GET", "/balance")

    async def _refresh_cache(self):
        """Fetch all products across pages and cache them by ID."""
        import time
        now = time.time()
        if now - self._cache_time < self._cache_ttl and self._product_cache:
            return
        cache = {}
        for page in range(1, 25):
            params = f"?page={page}" if page > 1 else ""
            result = await self._request("GET", f"/products{params}")
            if not result["success"]:
                break
            items = result["data"].get("results", [])
            if not items:
                break
            for p in items:
                cache[p["id"]] = p
        if cache:
            self._product_cache = cache
            self._cache_time = now

    async def find_product(self, product_id: int) -> dict:
        """Find a product by ID using cache. Returns dict or None."""
        import time
        # Check cache first
        if product_id in self._product_cache and (time.time() - self._cache_time) < self._cache_ttl:
            return self._product_cache[product_id]
        # Refresh cache and try again
        await self._refresh_cache()
        return self._product_cache.get(product_id)


# Singleton instance
api_client = APIClient()
