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

    async def get_customer_transactions(self, offset: int = 0) -> Dict:
        return await self._request("GET", f"/customer-transactions?offset={offset}")

    async def get_payment_methods(self) -> Dict:
        return await self._request("GET", "/payment-methods")

    async def recharge_cryptomus(self, amount: float) -> Dict:
        """Generate a Cryptomus payment URL for the given amount. The balance is
        credited automatically once the payment is made."""
        return await self._request("POST", "/recharge-cryptomus", {"amount": float(amount)})

    async def recharge_payeer(self, amount: float, trx_id: str) -> Dict:
        """Claim a Payeer payment already made. Credits the balance immediately."""
        return await self._request("POST", "/recharge-payeer",
                                   {"amount": float(amount), "trx_id": trx_id})

    async def get_parent_proxies(self, pkg_id: int, country_id: int = None) -> Dict:
        """List available parent proxies for a package (optionally a country)."""
        if not await self._ensure_token():
            return await self.login()
        query = f"?offset=0&pkg_id={pkg_id}"
        if country_id:
            query += f"&country_id={country_id}"
        return await self._request("GET", f"/parent-proxies{query}")

    async def check_username(self, username: str) -> Dict:
        """Check if a username is available or already registered."""
        return await self._request("GET", f"/check-username?username={username}")

    async def create_proxy(self, parent_proxy_id: int, package_id: int,
                           protocol: str, duration: float,
                           username: str = None, password: str = None,
                           ip_addr: str = None) -> Dict:
        """Create a new proxy account. Duration is in days (>=1) or hours (<1).

        User/pass packages (Golden=1, Silver=2, Turbo=4) require a username and
        password; if none given a random one is generated and its availability
        is verified with /check-username. Injection packages (Injection=3,
        Turbo Injection=5) require an ip_addr instead.
        """
        if not await self._ensure_token():
            return await self.login()
        data = {
            "parent_proxy_id": parent_proxy_id,
            "package_id": package_id,
            "protocol": protocol,
            # Duration must be a 2-decimal string: "1.00" = 1 day, "0.12" = 12 hours
            "duration": f"{float(duration):.2f}"
        }
        if package_id not in (3, 5):
            if password is None:
                password = self._random_string(12)
            if username is None:
                # Generate a username that is not already taken
                for _ in range(5):
                    username = self._random_string(8)
                    check = await self._check_username_available(username)
                    if check:
                        break
            data["username"] = username
            data["password"] = password
        elif ip_addr:
            data["ip_addr"] = ip_addr

        result = await self._request("POST", "/proxies", data)
        if result["success"] and isinstance(result.get("data"), dict) \
                and result["data"].get("result") is False:
            detail = result["data"].get("detail") or result["data"].get("message")
            if not detail:
                detail = "Proxy creation rejected by the API"
            return {"success": False, "code": 0, "data": result["data"], "detail": detail}
        return result

    async def _check_username_available(self, username: str) -> bool:
        """Return True if the username may be used. The API responds with
        {"result":"AVAILABLE"} or {"result":"ALREADY_USED"}."""
        try:
            result = await self._request("GET", f"/check-username?username={username}")
            if not result["success"]:
                return True
            body = result.get("data")
            def _taken(v):
                s = (v or "").strip().lower()
                return "already" in s or s.startswith("not available")
            if isinstance(body, dict):
                for v in body.values():
                    if isinstance(v, str) and _taken(v):
                        return False
            elif isinstance(body, str) and _taken(body):
                return False
            return True
        except Exception:
            return True

    @staticmethod
    def _random_string(length: int) -> str:
        import random
        import string
        alphabet = string.ascii_lowercase + string.digits
        return "".join(random.SystemRandom().choice(alphabet) for _ in range(length))


proxy_api = ProxyAPIClient()
