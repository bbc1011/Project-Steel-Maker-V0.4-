from urllib.parse import quote

import requests
from requests_oauthlib import OAuth1

class BrickLinkClient:
    BASE_URL = "https://api.bricklink.com/api/store/v1"

    def __init__(
        self,
        consumer_key,
        consumer_secret,
        token_value,
        token_secret,
        database,
        cache_hours=6,
        currency_code="USD",
        country_code="",
    ):
        self.auth = OAuth1(
            consumer_key,
            client_secret=consumer_secret,
            resource_owner_key=token_value,
            resource_owner_secret=token_secret,
            signature_method="HMAC-SHA1",
            signature_type="AUTH_HEADER",
        )
        self.database = database
        self.cache_seconds = float(cache_hours) * 3600
        self.currency_code = currency_code
        self.country_code = country_code

    def current_average_used_price(self, minifig_id):
        cached = self.database.get_cached_price(
            minifig_id,
            self.cache_seconds,
        )
        if cached:
            return cached

        item_no = quote(str(minifig_id), safe="")
        url = f"{self.BASE_URL}/items/MINIFIG/{item_no}/price"

        params = {
            "guide_type": "stock",
            "new_or_used": "U",
            "currency_code": self.currency_code,
        }
        if self.country_code:
            params["country_code"] = self.country_code

        r = requests.get(
            url,
            auth=self.auth,
            params=params,
            timeout=30,
        )
        r.raise_for_status()

        payload = r.json()
        if payload.get("meta", {}).get("code") not in (None, 200):
            raise RuntimeError(
                f"BrickLink error: {payload.get('meta')}"
            )

        data = payload.get("data", {})
        avg = data.get("avg_price")
        if avg in (None, ""):
            return None

        result = {
            "avg_price": float(avg),
            "currency_code": data.get(
                "currency_code",
                self.currency_code,
            ),
            "unit_quantity": data.get("unit_quantity"),
            "total_quantity": data.get("total_quantity"),
            "min_price": float(data.get("min_price", 0) or 0),
            "max_price": float(data.get("max_price", 0) or 0),
            "qty_avg_price": float(
                data.get("qty_avg_price", 0) or 0
            ),
            "cached": False,
        }

        self.database.cache_price(minifig_id, result)
        return result
