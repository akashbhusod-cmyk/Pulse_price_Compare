from __future__ import annotations

import json
import math
from urllib.parse import quote_plus

from pricepulse_compare.models import Offer, ProviderResult
from pricepulse_compare.services.providers.base import SearchProvider
from pricepulse_compare.settings import AppSettings


class DemoProvider(SearchProvider):
    provider_name = "demo"
    platform_order = [
        "Amazon",
        "Flipkart",
        "Croma",
        "Reliance Digital",
        "Vijay Sales",
    ]
    search_url_templates = {
        "Amazon": "https://www.amazon.in/s?k={query}",
        "Flipkart": "https://www.flipkart.com/search?q={query}",
        "Croma": "https://www.croma.com/searchB?q={query}",
        "Reliance Digital": "https://www.reliancedigital.in/search?q={query}",
        "Vijay Sales": "https://www.vijaysales.com/search/{query}",
    }

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def search(self, query: str) -> ProviderResult:
        catalog = json.loads(self.settings.demo_catalog_path.read_text(encoding="utf-8"))
        query_tokens = {token for token in query.lower().split() if token}

        matches: list[Offer] = []
        for item in catalog:
            searchable = f"{item['title']} {item['brand']} {item['category']} {item['source']}".lower()
            token_hits = sum(1 for token in query_tokens if token in searchable)
            required_hits = max(1, math.ceil(len(query_tokens) * 0.6)) if query_tokens else 0
            if query_tokens and query.lower() not in searchable and token_hits < required_hits:
                continue

            matches.append(
                Offer(
                    title=item["title"],
                    source=item["source"],
                    platform=item["source"],
                    price=float(item["price"]),
                    old_price=float(item["old_price"]) if item.get("old_price") else None,
                    currency=item.get("currency", "INR"),
                    product_url=self._normalize_product_url(
                        item["source"],
                        item.get("product_url"),
                        item["title"],
                    ),
                    image_url=item.get("image_url"),
                    rating=float(item["rating"]) if item.get("rating") is not None else None,
                    reviews=int(item["reviews"]) if item.get("reviews") is not None else None,
                    delivery=item.get("delivery"),
                    provider=self.provider_name,
                    source_type="demo-catalog",
                )
            )

        matches.sort(key=lambda offer: offer.price)

        if matches:
            message = (
                "Showing bundled sample catalog results for this query. "
                "Add live API keys in .env for real-time marketplace listings."
            )
        else:
            message = (
                "No demo catalog entry matched this search. "
                "Add a live provider key or search for a sample product such as iPhone 15, HP Victus, or Dell Inspiron."
            )

        return ProviderResult(
            provider=self.provider_name,
            offers=matches[: self.settings.result_limit],
            live=False,
            message=message,
        )

    def _normalize_product_url(self, source: str, current_url: str | None, query: str) -> str:
        if current_url and current_url.rstrip("/") not in {
            "https://www.amazon.in",
            "https://www.flipkart.com",
            "https://www.croma.com",
            "https://www.reliancedigital.in",
            "https://www.vijaysales.com",
        }:
            return current_url
        return self._build_search_url(source, query)

    def _build_search_url(self, source: str, query: str) -> str:
        template = self.search_url_templates.get(source, "https://www.google.com/search?q={query}")
        return template.format(query=quote_plus(query))
