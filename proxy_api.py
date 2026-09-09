import time
import json
import asyncio
import os
import urllib.request
import urllib.error
from typing import Dict
from dotenv import load_dotenv

load_dotenv()

PROXY_API_BASE = os.getenv("PROXY_API_BASE", "https://bot.mega-panel.net/api/web/index.php/v1")
PROXY_API_EMAIL = os.getenv("PROXY_API_EMAIL", "")
PROXY_API_PASSWORD = os.getenv("PROXY_API_PASSWORD", "")

# Only these package ids are sold in the bot (Golden=1, Silver=2)
BOT_PACKAGE_IDS = [1, 2]


class ProxyAPIClient:
    """Client for the mega-panel proxy reseller API."""

    def __init__(self):
        self.base_url = PROXY_API_BASE
        self.email = PROXY_API_EMAIL
        self.password = PROXY_API_PASSWORD
        self._token = None
        self._token_expire = 0
        self._cache = {}
        self._cache_time = 0
        self._cache_ttl = 120

    def _request_sync(self, method: str, endpoint: str, data: dict = None, token: bool = True) -> Dict:
        """Make a synchronous API request using stdlib urllib."""
        url = self.base_url + endpoint
        headers = {"Content-Type": "application/json"}
        if token and self._token:
            headers["Authorization"] = "Bearer " + self._token

        body = json.dumps(data).encode("utf-8") if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                return {"success": True, "data": result}
        except urllib.error.HTTPError as e:
            try:
                result = json.loads(e.read().decode("utf-8"))
            except Exception:
                result = {}
            return {"success": False, "code": e.code, "data": result,
                    "detail": result.get("error") or result.get("message") or f"HTTP error {e.code}"}
        except urllib.error.URLError as e:
            return {"success": False, "code": 0, "data": {},
                    "detail": "Failed to connect to proxy API: " + str(e.reason)}
        except Exception as e:
            return {"success": False, "code": 0, "data": {}, "detail": str(e)}

    async def _request(self, method: str, endpoint: str, data: dict = None, token: bool = True) -> Dict:
        return await asyncio.to_thread(self._request_sync, method, endpoint, data, token)

    def _login_sync(self) -> Dict:
        """Perform login synchronously and store token."""
        url = self.base_url + "/login"
        body = json.dumps({
            "email": self.email,
            "password": self.password
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                token = result.get("token")
                expire = result.get("expire_at", 0)
                if not token:
                    return {"success": False, "detail": "Login returned no token"}
                self._token = token
                self._token_expire = int(expire)
                return {"success": True, "data": result}
        except urllib.error.HTTPError as e:
            try:
                result = json.loads(e.read().decode("utf-8"))
            except Exception:
                result = {}
            self._token = None
            return {"success": False, "code": e.code, "data": result,
                    "detail": result.get("error") or result.get("message") or f"HTTP error {e.code}"}
        except urllib.error.URLError as e:
            return {"success": False, "detail": "Connection error: " + str(e.reason)}
        except Exception as e:
            return {"success": False, "detail": str(e)}

    async def login(self) -> Dict:
        """Ensure we have a valid token (log in if expired)."""
        if self._token and time.time() < self._token_expire - 60:
            return {"success": True}
        return await asyncio.to_thread(self._login_sync)

    async def _ensure_token(self) -> bool:
        res = await self.login()
        return res["success"]

    def _get_cached(self, key: str):
        now = time.time()
        if now - self._cache_time < self._cache_ttl and key in self._cache:
            return self._cache[key]
        return None

    def _set_cache(self, key: str, value):
        self._cache[key] = value
        self._cache_time = time.time()

    async def _get_json(self, endpoint: str, key: str):
        cached = self._get_cached(key)
        if cached is not None:
            return {"success": True, "data": cached}
        if not await self._ensure_token():
            return await self.login()
        result = await self._request("GET", endpoint)
        if result["success"]:
            self._set_cache(key, result["data"])
        return result

    async def get_packages(self) -> Dict:
        return await self._get_json("/packages", "packages")

    async def get_prices(self, pkg_id: int) -> Dict:
        return await self._get_json(f"/prices?pkg_id={pkg_id}", f"prices_{pkg_id}")

    async def get_countries(self, pkg_id: int) -> Dict:
        return await self._get_json(f"/countries?pkg_id={pkg_id}", f"countries_{pkg_id}")

    async def get_country_stats(self) -> Dict:
        return await self._get_json("/country-stats", "country_stats")

    async def get_balance(self) -> Dict:
        result = await self._request("GET", "/balance")
        if not result["success"] and time.time() >= self._token_expire:
            await self.login()
            result = await self._request("GET", "/balance")
        return result

    async def get_parent_proxies(self, pkg_id: int, country_id: int = None) -> Dict:
        """List available parent proxies for a package (optionally a country)."""
        if not await self._ensure_token():
            return await self.login()
        query = f"?offset=0&pkg_id={pkg_id}"
        if country_id:
            query += f"&country_id={country_id}"
        return await self._request("GET", f"/parent-proxies{query}")

    async def create_proxy(self, parent_proxy_id: int, package_id: int,
                           protocol: str, duration: float) -> Dict:
        """Create a new proxy account. Duration is in days (>=1) or hours (<1)."""
        if not await self._ensure_token():
            return await self.login()
        data = {
            "parent_proxy_id": parent_proxy_id,
            "package_id": package_id,
            "protocol": protocol,
            "duration": duration
        }
        result = await self._request("POST", "/proxies", data)
        if result["success"] and isinstance(result.get("data"), dict) \
                and result["data"].get("result") is False:
            return {"success": False, "code": 0, "data": result["data"],
                    "detail": "Proxy creation rejected by the API"}
        return result


proxy_api = ProxyAPIClient()
