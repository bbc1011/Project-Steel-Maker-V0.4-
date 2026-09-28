import base64
from urllib.parse import quote

import requests

class EbayClient:
    TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
    SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    ITEM_URL = "https://api.ebay.com/buy/browse/v1/item"

    def __init__(self, client_id, client_secret, marketplace_id="EBAY_US"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.marketplace_id = marketplace_id
        self.token = None

    def _get_token(self):
        credentials = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode()
        ).decode()

        r = requests.post(
            self.TOKEN_URL,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
            timeout=30,
        )
        r.raise_for_status()
        self.token = r.json()["access_token"]

    def _headers(self):
        if not self.token:
            self._get_token()
        return {
            "Authorization": f"Bearer {self.token}",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
        }

    @staticmethod
    def _range(name, low, high):
        if low is None and high is None:
            return None
        if low is None:
            return f"{name}:[..{high}]"
        if high is None:
            return f"{name}:[{low}]"
        return f"{name}:[{low}..{high}]"

    @staticmethod
    def _set(name, values):
        return f"{name}:{{{'|'.join(str(v) for v in values)}}}"

    def _build_filters(self, f):
        parts = []

        price = self._range(
            "price",
            f.get("min_price_usd"),
            f.get("max_price_usd"),
        )
        if price:
            parts.append(price)
            parts.append(f"priceCurrency:{f.get('price_currency', 'USD')}")

        bid_count = self._range(
            "bidCount",
            f.get("min_bid_count"),
            f.get("max_bid_count"),
        )
        if bid_count:
            parts.append(bid_count)

        start_date = self._range(
            "itemStartDate",
            f.get("item_start_date_from"),
            f.get("item_start_date_to"),
        )
        if start_date:
            parts.append(start_date)

        end_date = self._range(
            "itemEndDate",
            f.get("item_end_date_from"),
            f.get("item_end_date_to"),
        )
        if end_date:
            parts.append(end_date)

        list_filters = {
            "buying_options": "buyingOptions",
            "condition_ids": "conditionIds",
            "conditions": "conditions",
            "delivery_options": "deliveryOptions",
            "exclude_category_ids": "excludeCategoryIds",
            "exclude_sellers": "excludeSellers",
            "payment_methods": "paymentMethods",
            "qualified_programs": "qualifiedPrograms",
            "seller_account_types": "sellerAccountTypes",
            "sellers": "sellers",
        }
        for key, api_name in list_filters.items():
            value = f.get(key)
            if value:
                if not isinstance(value, list):
                    value = [value]
                parts.append(self._set(api_name, value))

        scalar_filters = {
            "delivery_country": "deliveryCountry",
            "delivery_postal_code": "deliveryPostalCode",
            "item_location_country": "itemLocationCountry",
            "item_location_region": "itemLocationRegion",
            "pickup_country": "pickupCountry",
            "pickup_postal_code": "pickupPostalCode",
            "pickup_radius": "pickupRadius",
            "pickup_radius_unit": "pickupRadiusUnit",
        }
        for key, api_name in scalar_filters.items():
            value = f.get(key)
            if value not in (None, ""):
                parts.append(f"{api_name}:{value}")

        true_only_filters = {
            "charity_only": "charityOnly",
            "priority_listing": "priorityListing",
            "returns_accepted": "returnsAccepted",
            "search_in_description": "searchInDescription",
        }
        for key, api_name in true_only_filters.items():
            if f.get(key) is True:
                parts.append(f"{api_name}:true")

        if f.get("free_shipping") is True:
            parts.append("maxDeliveryCost:0")

        for raw in f.get("raw_filters", []):
            raw = str(raw).strip()
            if raw:
                parts.append(raw)

        return ",".join(parts)

    @staticmethod
    def _shipping(item):
        options = item.get("shippingOptions") or []
        if not options:
            return 0.0
        return float(
            options[0].get("shippingCost", {}).get("value", 0) or 0
        )

    @staticmethod
    def _image_urls(item):
        images = []
        primary = item.get("image", {}).get("imageUrl")
        if primary:
            images.append(primary)
        for extra in item.get("additionalImages", []) or []:
            url = extra.get("imageUrl")
            if url and url not in images:
                images.append(url)
        return images

    def _normalize_item(self, item):
        current_bid = item.get("currentBidPrice") or {}
        price = item.get("price") or {}
        return {
            "item_id": item.get("itemId"),
            "title": item.get("title", ""),
            "price": float(price.get("value", 0) or 0),
            "shipping": self._shipping(item),
            "currency": price.get("currency", "USD"),
            "current_bid_price": (
                float(current_bid.get("value"))
                if current_bid.get("value") not in (None, "")
                else None
            ),
            "current_bid_currency": current_bid.get("currency"),
            "bid_count": int(item.get("bidCount", 0) or 0),
            "buying_options": list(item.get("buyingOptions") or []),
            "item_end_date": item.get("itemEndDate"),
            "item_creation_date": item.get("itemCreationDate"),
            "item_web_url": item.get("itemWebUrl", ""),
            "image_urls": self._image_urls(item),
            "condition": item.get("condition"),
            "item_location": item.get("itemLocation"),
            "seller": item.get("seller"),
        }

    def search(self, query, filters=None, max_results=20):
        f = filters or {}
        params = {
            "q": query,
            "limit": min(max(1, int(max_results)), 200),
        }

        built = self._build_filters(f)
        if built:
            params["filter"] = built

        if f.get("category_ids"):
            value = f["category_ids"]
            params["category_ids"] = (
                ",".join(map(str, value))
                if isinstance(value, list)
                else str(value)
            )

        for key in ("gtin", "epid", "charity_ids", "aspect_filter"):
            if f.get(key):
                params[key] = f[key]

        if f.get("sort"):
            params["sort"] = f["sort"]

        if f.get("fieldgroups"):
            value = f["fieldgroups"]
            params["fieldgroups"] = (
                ",".join(value) if isinstance(value, list) else value
            )

        r = requests.get(
            self.SEARCH_URL,
            headers=self._headers(),
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        return [
            self._normalize_item(item)
            for item in r.json().get("itemSummaries", [])
        ]

    def get_item(self, item_id):
        safe_id = quote(str(item_id), safe="|")
        r = requests.get(
            f"{self.ITEM_URL}/{safe_id}",
            headers=self._headers(),
            timeout=30,
        )
        r.raise_for_status()
        return self._normalize_item(r.json())

    def enrich_listing(self, summary):
        """Fetch full item details once so the vision pipeline gets all photos."""
        try:
            full = self.get_item(summary["item_id"])
            # Keep useful summary values when the item endpoint omits them.
            for key, value in summary.items():
                if full.get(key) in (None, "", [], {}):
                    full[key] = value
            return full
        except Exception as exc:
            print(f"  eBay detail lookup failed; using search summary: {exc}")
            return summary
