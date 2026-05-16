from __future__ import annotations

import json
import math
import re
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
    stop_words = {
        "a",
        "an",
        "and",
        "best",
        "below",
        "buy",
        "compare",
        "deal",
        "deals",
        "find",
        "for",
        "good",
        "in",
        "less",
        "me",
        "near",
        "on",
        "price",
        "products",
        "search",
        "shop",
        "show",
        "than",
        "the",
        "to",
        "under",
        "with",
    }
    category_aliases = {
        "audio": {"audio", "earbuds", "headphone", "headphones", "speaker"},
        "laptop": {"gaming laptop", "laptop", "laptops", "notebook"},
        "shoes": {"shoe", "shoes", "sneaker", "sneakers", "running shoes"},
        "smartphone": {"5g phone", "mobile", "mobile phone", "phone", "smartphone", "smartphones"},
        "tv": {"smart tv", "television", "tv"},
    }
    budget_pattern = re.compile(
        r"(?:(?:under|below|less than|max|max\.|upto|up to)\s*₹?\s*([0-9][0-9,]*))|(?:₹\s*([0-9][0-9,]*))"
    )

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def search(self, query: str) -> ProviderResult:
        catalog = json.loads(self.settings.demo_catalog_path.read_text(encoding="utf-8"))
        query_context = self._build_query_context(query)
        query_tokens = query_context["tokens"]
        category_filters = query_context["categories"]
        max_price = query_context["max_price"]

        matches = self._match_catalog(
            catalog,
            query=query,
            query_tokens=query_tokens,
            category_filters=category_filters,
            max_price=max_price,
        )

        matches.sort(key=lambda offer: offer.price)

        if matches:
            message = (
                "Showing bundled sample catalog results for this query. "
                "Add live API keys in .env for real-time marketplace listings."
            )
        else:
            if max_price is not None and category_filters:
                message = (
                    "No demo catalog items matched this budget. "
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

    @classmethod
    def _build_query_context(cls, query: str) -> dict[str, object]:
        normalized = query.lower().strip()
        raw_tokens = re.findall(r"[a-z0-9]+", normalized)
        category_filters = cls._extract_categories(normalized)
        max_price = cls._extract_max_price(normalized)

        query_tokens = {
            token
            for token in raw_tokens
            if token
            and not token.isdigit()
            and token not in cls.stop_words
        }

        for category in category_filters:
            query_tokens.discard(category)

        return {
            "tokens": query_tokens,
            "categories": category_filters,
            "max_price": max_price,
        }

    def _match_catalog(
        self,
        catalog: list[dict[str, object]],
        *,
        query: str,
        query_tokens: set[str],
        category_filters: set[str],
        max_price: float | None,
    ) -> list[Offer]:
        matches: list[Offer] = []
        required_hits = self._required_hits(query_tokens, category_filters)

        for item in catalog:
            item_category = str(item.get("category", "")).lower()
            item_price = float(item["price"])
            if category_filters and item_category not in category_filters:
                continue
            if max_price is not None and item_price > max_price:
                continue

            searchable = f"{item['title']} {item['brand']} {item['category']} {item['source']}".lower()
            token_hits = sum(1 for token in query_tokens if token in searchable)
            if query_tokens and query.lower() not in searchable and token_hits < required_hits:
                continue

            matches.append(
                Offer(
                    title=item["title"],
                    source=item["source"],
                    platform=item["source"],
                    price=item_price,
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

        return matches

    @classmethod
    def _extract_categories(cls, normalized_query: str) -> set[str]:
        matches: set[str] = set()
        for category, aliases in cls.category_aliases.items():
            if any(alias in normalized_query for alias in aliases):
                matches.add(category)
        return matches

    @classmethod
    def _extract_max_price(cls, normalized_query: str) -> float | None:
        match = cls.budget_pattern.search(normalized_query)
        if not match:
            return None

        raw_value = next((group for group in match.groups() if group), "")
        cleaned = raw_value.replace(",", "")
        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def _required_hits(query_tokens: set[str], category_filters: set[str]) -> int:
        if not query_tokens:
            return 0 if category_filters else 1
        return max(1, math.ceil(len(query_tokens) * 0.6))

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
