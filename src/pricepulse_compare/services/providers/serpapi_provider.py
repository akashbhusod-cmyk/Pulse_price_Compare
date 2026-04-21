from __future__ import annotations

from collections.abc import Iterable
import math
import re
from urllib.parse import urlparse

import requests

from pricepulse_compare.models import Offer, ProviderResult
from pricepulse_compare.services.providers.base import SearchProvider
from pricepulse_compare.settings import AppSettings


class SerpApiProvider(SearchProvider):
    provider_name = "serpapi"
    endpoint = "https://serpapi.com/search.json"
    accessory_keywords = {
        "case",
        "cover",
        "flip cover",
        "back cover",
        "screen guard",
        "screen protector",
        "tempered glass",
        "charger",
        "adapter",
        "cable",
        "wire",
        "earbuds",
        "headphones",
        "headset",
        "skin",
        "bumper",
        "wallet case",
        "pouch",
        "stand",
        "holder",
        "camera lens protector",
        "protector",
        "silicone",
    }
    optional_query_tokens = {"5g", "4g", "wifi", "cellular", "dual", "sim"}
    stop_tokens = {"phone", "mobile", "smartphone", "new", "latest"}
    must_keep_tokens = {"pro", "plus", "max", "ultra", "mini", "note", "fe", "air"}
    excluded_title_keywords = {
        "sell ",
        "exchange",
        "replacement",
        "repair",
        "spare",
        "housing",
        "display combo",
        "battery for",
        "refurbished",
        "renewed",
        "used ",
        "pre-owned",
    }
    phone_brands = {
        "apple", "iphone", "samsung", "vivo", "oppo", "oneplus", "xiaomi",
        "redmi", "realme", "iqoo", "motorola", "nokia", "pixel", "google",
        "honor", "nothing",
    }
    laptop_brands = {"dell", "hp", "lenovo", "asus", "acer", "msi", "apple", "macbook"}
    tv_terms = {"tv", "television", "smart tv", "oled", "qled"}
    trusted_platforms = {
        "amazon": {"amazon", "amazon.in"},
        "flipkart": {"flipkart"},
        "mi": {"mi", "mi.com", "xiaomi", "xiaomi india"},
        "croma": {"croma"},
        "reliance digital": {"reliance digital", "reliancedigital"},
        "jiomart": {"jiomart", "jiomart electronics"},
        "vijay sales": {"vijay sales", "vijaysales"},
        "tata cliq": {"tata cliq", "tatacliq"},
        "bajaj mall": {"bajaj mall", "bajaj markets x ondc"},
        "poorvika": {"poorvika"},
        "sangeetha": {"sangeetha"},
        "vasanth and co": {"vasanth and co"},
        "sathya": {"sathya", "sathya retail"},
        "vivo": {"vivo", "vivo mobile india"},
        "samsung": {"samsung", "samsung india"},
        "oneplus": {"oneplus", "oneplus india"},
        "apple": {"apple", "apple india"},
    }
    platform_display_names = {
        "amazon": "Amazon",
        "flipkart": "Flipkart",
        "mi": "Mi.com",
        "croma": "Croma",
        "reliance digital": "Reliance Digital",
        "jiomart": "JioMart",
        "vijay sales": "Vijay Sales",
        "tata cliq": "Tata CLiQ",
        "bajaj mall": "Bajaj Mall",
        "poorvika": "Poorvika",
        "sangeetha": "Sangeetha",
        "vasanth and co": "Vasanth and Co",
        "sathya": "Sathya",
        "vivo": "vivo",
        "samsung": "Samsung",
        "oneplus": "OnePlus",
        "apple": "Apple",
    }

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def search(self, query: str) -> ProviderResult:
        if not self.settings.serpapi_key:
            return ProviderResult(
                provider=self.provider_name,
                live=False,
                message="SerpApi key not configured. Add SERPAPI_KEY in .env to enable live marketplace results.",
            )

        last_error: str | None = None
        for search_query in self._build_search_queries(query):
            try:
                payload = self._request(
                    {
                        "engine": "google_shopping",
                        "q": search_query,
                        "location": self.settings.default_location,
                        "gl": self.settings.default_country,
                        "hl": self.settings.default_language,
                        "num": self.settings.result_limit,
                        **self._search_filters(query),
                    }
                )
            except requests.RequestException as exc:
                last_error = str(exc)
                continue

            offers = self._expand_search_results(payload, query)
            if offers:
                return ProviderResult(
                    provider=self.provider_name,
                    offers=offers[: self.settings.result_limit],
                    live=True,
                    message="Live Google Shopping results from SerpApi.",
                )

        return ProviderResult(
            provider=self.provider_name,
            offers=[],
            live=True,
            error=last_error,
            message="SerpApi returned no exact trusted marketplace listings for this product query.",
        )

    def _request(self, params: dict[str, object]) -> dict[str, object]:
        request_params = dict(params)
        request_params["api_key"] = self.settings.serpapi_key
        response = requests.get(self.endpoint, params=request_params, timeout=self.settings.request_timeout)
        response.raise_for_status()
        return response.json()

    def _expand_search_results(self, payload: dict[str, object], query: str) -> list[Offer]:
        offers: list[Offer] = []
        search_results = payload.get("shopping_results", [])
        if not isinstance(search_results, list):
            return offers

        for index, item in enumerate(search_results[: self.settings.result_limit]):
            if not isinstance(item, dict):
                continue

            fallback_offer = self._offer_from_search_item(item)
            if fallback_offer is None:
                continue

            if index < self.settings.serpapi_max_product_details and self._matching_offers(query, [fallback_offer], strict=True):
                store_offers = self._fetch_store_offers(item)
                relevant_store_offers = self._matching_offers(query, store_offers, strict=True)
                if relevant_store_offers:
                    offers.extend(relevant_store_offers)
                    if not self._contains_same_listing(relevant_store_offers, fallback_offer):
                        offers.append(fallback_offer)
                    continue

            offers.append(fallback_offer)

        return self._filter_and_rank_offers(query, offers)

    def _fetch_store_offers(self, item: dict[str, object]) -> list[Offer]:
        page_token = self._extract_page_token(item)
        if not page_token:
            return []

        offers: list[Offer] = []
        current_token = page_token
        pages_remaining = max(1, self.settings.serpapi_store_pages)

        while current_token and pages_remaining > 0 and len(offers) < self.settings.result_limit:
            try:
                payload = self._request(
                    {
                        "engine": "google_immersive_product",
                        "page_token": current_token,
                        "gl": self.settings.default_country,
                        "hl": self.settings.default_language,
                        "location": self.settings.default_location,
                        "more_stores": "true",
                    }
                )
            except requests.RequestException:
                break

            offers.extend(self._offers_from_immersive_payload(payload, item))
            current_token = self._extract_next_store_page_token(payload)
            pages_remaining -= 1

        return offers

    def _offer_from_search_item(self, item: dict[str, object]) -> Offer | None:
        price = self.extract_price(item.get("extracted_price") or item.get("price"))
        if price is None:
            return None

        product_url = self._preferred_link(item)
        source = item.get("source") or self.derive_platform_name(None, product_url)
        platform = self._canonical_platform_name(str(source), product_url)
        return Offer(
            title=item.get("title", "Unknown product"),
            source=str(source),
            platform=platform,
            price=price,
            old_price=self.extract_price(item.get("extracted_old_price") or item.get("old_price")),
            currency="INR" if self.settings.default_country == "in" else str(item.get("currency", "USD")),
            product_url=product_url,
            image_url=item.get("thumbnail"),
            rating=self._to_float(item.get("rating")),
            reviews=self._to_int(item.get("reviews")),
            delivery=item.get("delivery"),
            provider=self.provider_name,
            source_type="live-search",
        )

    def _offers_from_immersive_payload(
        self,
        payload: dict[str, object],
        search_item: dict[str, object],
    ) -> list[Offer]:
        product_results = payload.get("product_results", {})
        if not isinstance(product_results, dict):
            return []

        stores = product_results.get("stores", [])
        if not isinstance(stores, list):
            return []

        title = str(product_results.get("title") or search_item.get("title") or "Unknown product")
        thumbnail = product_results.get("thumbnail") or search_item.get("thumbnail")
        offers: list[Offer] = []

        for store in stores:
            if not isinstance(store, dict):
                continue

            primary_offer = store.get("primary_offer") if isinstance(store.get("primary_offer"), dict) else {}
            price = self.extract_price(
                store.get("extracted_price")
                or store.get("price")
                or primary_offer.get("price")
            )
            if price is None:
                continue

            link = self._store_link(store, search_item)
            merchant = self._store_name(store, link)
            platform = self._canonical_platform_name(merchant, link)
            offer_title = str(store.get("title") or title)

            offers.append(
                Offer(
                    title=offer_title,
                    source=merchant,
                    platform=platform,
                    price=price,
                    old_price=self.extract_price(store.get("old_price") or store.get("extracted_old_price")),
                    currency=str(store.get("currency") or ("INR" if self.settings.default_country == "in" else "USD")),
                    product_url=link,
                    image_url=thumbnail,
                    rating=self._to_float(store.get("rating")),
                    reviews=self._to_int(store.get("reviews") or store.get("rating_count")),
                    delivery=str(store.get("shipping") or store.get("delivery") or "") or None,
                    provider=self.provider_name,
                    source_type="live-store",
                )
            )

        return offers

    def _filter_and_rank_offers(self, query: str, offers: list[Offer]) -> list[Offer]:
        if not offers:
            return []

        strict = self._matching_offers(query, offers, strict=True)
        if strict:
            trusted = self._trusted_offers(query, strict)
            return trusted if trusted else []

        relaxed = self._matching_offers(query, offers, strict=False)
        if relaxed:
            trusted = self._trusted_offers(query, relaxed)
            return trusted if trusted else []

        return []

    def _matching_offers(self, query: str, offers: list[Offer], strict: bool) -> list[Offer]:
        query_tokens = self._query_tokens(query)
        required_tokens = self._required_query_tokens(query_tokens)
        accessory_query = self._is_accessory_query(query)
        minimum_price = self._minimum_expected_price(query)
        query_variants = set(required_tokens)

        matched: list[tuple[int, int, Offer]] = []
        for offer in offers:
            title = offer.title.lower()
            title_tokens = self._query_tokens(title)
            compact_title = self._compact_text(title)
            important_tokens = [token for token in required_tokens if token in self.must_keep_tokens]

            if not accessory_query and self._is_accessory_title(title):
                continue
            if any(keyword in title for keyword in self.excluded_title_keywords):
                continue
            if self._has_variant_mismatch(query_variants, title_tokens, title):
                continue
            if minimum_price is not None and offer.price < minimum_price:
                continue

            token_hits = sum(
                1 for token in required_tokens if self._token_matches(token, title_tokens, title, compact_title)
            )
            if strict:
                if required_tokens and not all(
                    self._token_matches(token, title_tokens, title, compact_title) for token in required_tokens
                ):
                    continue
            else:
                minimum_hits = max(1, math.ceil(len(required_tokens) * 0.6)) if required_tokens else 0
                if required_tokens and token_hits < minimum_hits:
                    continue
                if important_tokens and not all(
                    self._token_matches(token, title_tokens, title, compact_title) for token in important_tokens
                ):
                    continue

            score = self._relevance_score(query, offer.title)
            matched.append((score, token_hits, offer))

        matched.sort(key=lambda item: (-item[0], -item[1], item[2].price))
        return [offer for _, _, offer in matched]

    def _trusted_offers(self, query: str, offers: list[Offer]) -> list[Offer]:
        if not self._looks_like_phone_query(query) or self._is_accessory_query(query):
            return offers

        trusted = [offer for offer in offers if self._trusted_platform_key(offer.platform, offer.product_url)]
        trusted.sort(
            key=lambda offer: (
                self._trusted_platform_rank(offer.platform, offer.product_url),
                offer.price,
            )
        )
        return trusted

    @staticmethod
    def _contains_same_listing(offers: list[Offer], target: Offer) -> bool:
        target_platform = target.platform.strip().lower()
        return any(
            offer.platform.strip().lower() == target_platform
            and abs(offer.price - target.price) < 1
            for offer in offers
        )

    def _relevance_score(self, query: str, title: str) -> int:
        query_lower = query.lower()
        title_lower = title.lower()
        score = 0

        if query_lower in title_lower:
            score += 50

        compact_query = self._compact_text(query_lower)
        compact_title = self._compact_text(title_lower)
        if compact_query and compact_query in compact_title:
            score += 40

        query_tokens = self._query_tokens(query_lower)
        for token in query_tokens:
            if self._token_matches(token, self._query_tokens(title_lower), title_lower, compact_title):
                score += 10

        if not self._is_accessory_query(query) and self._is_accessory_title(title_lower):
            score -= 100
        if any(keyword in title_lower for keyword in self.excluded_title_keywords):
            score -= 100

        for token in self._query_tokens(query_lower):
            if token in self.must_keep_tokens and token in title_lower:
                score += 15

        return score

    def _build_search_query(self, query: str) -> str:
        normalized = " ".join(query.split()).strip()
        if self._looks_like_phone_query(normalized) and not self._is_accessory_query(normalized):
            return f"\"{normalized}\" phone"
        if " " in normalized:
            return f"\"{normalized}\""
        return normalized

    def _build_search_queries(self, query: str) -> list[str]:
        normalized = " ".join(query.split()).strip()
        variants: list[str] = []

        if self._looks_like_phone_query(normalized) and not self._is_accessory_query(normalized):
            variants.append(f"\"{normalized}\" phone")
            variants.append(f"\"{normalized}\" smartphone")
            if "5g" not in normalized.lower():
                variants.append(f"\"{normalized} 5G\"")
            variants.append(f"\"{normalized}\"")
        else:
            variants.append(self._build_search_query(normalized))

        seen: set[str] = set()
        ordered: list[str] = []
        for variant in variants:
            if variant not in seen:
                seen.add(variant)
                ordered.append(variant)
        return ordered

    def _search_filters(self, query: str) -> dict[str, str]:
        query_lower = query.lower()
        tokens = set(self._query_tokens(query_lower))

        if self._is_accessory_query(query):
            return {}

        if tokens & self.phone_brands and any(char.isdigit() for char in query_lower):
            return {}

        if tokens & self.laptop_brands or "laptop" in query_lower or "macbook" in query_lower:
            return {}

        if any(term in query_lower for term in self.tv_terms):
            return {}

        return {}

    def _minimum_expected_price(self, query: str) -> float | None:
        query_lower = query.lower()
        tokens = set(self._query_tokens(query_lower))
        if self._is_accessory_query(query):
            return None
        if tokens & self.phone_brands and any(char.isdigit() for char in query_lower):
            return 5000
        if tokens & self.laptop_brands or "laptop" in query_lower or "macbook" in query_lower:
            return 15000
        if any(term in query_lower for term in self.tv_terms):
            return 8000
        return None

    def _looks_like_phone_query(self, query: str) -> bool:
        query_lower = query.lower()
        tokens = set(self._query_tokens(query_lower))
        return bool(tokens & self.phone_brands and any(char.isdigit() for char in query_lower))

    def _query_tokens(self, text: str) -> list[str]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        return [token for token in tokens if token not in self.stop_tokens]

    def _required_query_tokens(self, query_tokens: list[str]) -> list[str]:
        optional_tokens = set(self.optional_query_tokens)
        query_token_set = set(query_tokens)

        if "redmi" in query_token_set:
            optional_tokens.add("xiaomi")
        if "iphone" in query_token_set:
            optional_tokens.add("apple")
        if "pixel" in query_token_set:
            optional_tokens.add("google")

        return [token for token in query_tokens if token not in optional_tokens]

    def _has_variant_mismatch(self, query_tokens: set[str], title_tokens: list[str], title: str) -> bool:
        variant_tokens = {"pro", "plus", "max", "ultra", "mini", "fe", "lite", "se"}
        title_token_set = set(title_tokens)

        has_plus_variant = (
            "plus" in title_token_set
            or re.search(r"\b[a-z0-9]+\+", title) is not None
            or re.search(r"\bpro\s*\+", title) is not None
            or re.search(r"\bpro\s+plus\b", title) is not None
        )
        if "plus" not in query_tokens and has_plus_variant:
            return True

        for variant in variant_tokens - {"plus"}:
            if variant in title_token_set and variant not in query_tokens:
                return True

        return False

    def _token_matches(
        self,
        token: str,
        title_tokens: list[str],
        title: str,
        compact_title: str,
    ) -> bool:
        if token in title_tokens:
            return True

        if self._is_model_token(token):
            return False

        return token in title or token in compact_title

    @staticmethod
    def _is_model_token(token: str) -> bool:
        return any(char.isalpha() for char in token) and any(char.isdigit() for char in token)

    @staticmethod
    def _compact_text(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", text.lower())

    def _is_accessory_query(self, query: str) -> bool:
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in self.accessory_keywords)

    def _is_accessory_title(self, title: str) -> bool:
        return any(keyword in title for keyword in self.accessory_keywords)

    def _canonical_platform_name(self, source: str, url: str | None) -> str:
        key = self._trusted_platform_key(source, url)
        if key:
            return self.platform_display_names[key]
        return source.strip() or self.derive_platform_name(None, url)

    def _trusted_platform_rank(self, source: str, url: str | None) -> int:
        ordered = list(self.trusted_platforms.keys())
        key = self._trusted_platform_key(source, url)
        return ordered.index(key) if key in ordered else len(ordered)

    def _trusted_platform_key(self, source: str | None, url: str | None) -> str | None:
        source_key = self._normalize_platform_key(source)
        host_key = self._normalize_platform_key(urlparse(url).netloc if url else None)

        for canonical, aliases in self.trusted_platforms.items():
            for alias in aliases:
                alias_key = self._normalize_platform_key(alias)
                if source_key == alias_key or host_key == alias_key:
                    return canonical
                if source_key.endswith(alias_key) or host_key.endswith(alias_key):
                    return canonical

        return None

    @staticmethod
    def _normalize_platform_key(value: str | None) -> str:
        if not value:
            return ""
        normalized = value.lower().replace("www.", "")
        normalized = normalized.replace(".com", "").replace(".in", "")
        return re.sub(r"[^a-z0-9]+", " ", normalized).strip()

    @staticmethod
    def _extract_page_token(item: dict[str, object]) -> str | None:
        immersive = item.get("serpapi_immersive_product_api")
        if isinstance(immersive, dict):
            token = immersive.get("page_token") or immersive.get("token")
            if token:
                return str(token)
        token = item.get("immersive_product_page_token") or item.get("page_token")
        return str(token) if token else None

    @staticmethod
    def _extract_next_store_page_token(payload: dict[str, object]) -> str | None:
        product_results = payload.get("product_results", {})
        if not isinstance(product_results, dict):
            return None
        token = product_results.get("stores_next_page_token") or payload.get("stores_next_page_token")
        return str(token) if token else None

    def _preferred_link(self, item: dict[str, object]) -> str:
        candidate_links = [
            item.get("link"),
            item.get("merchant_link"),
            item.get("offer_link"),
            item.get("product_link"),
        ]
        for link in candidate_links:
            if isinstance(link, str) and link:
                return link
        return ""

    def _store_link(self, store: dict[str, object], search_item: dict[str, object]) -> str:
        candidate_links = [
            store.get("link"),
            store.get("merchant_link"),
            store.get("offer_link"),
            store.get("product_link"),
            store.get("store_link"),
            search_item.get("link"),
            search_item.get("merchant_link"),
            search_item.get("offer_link"),
            search_item.get("product_link"),
        ]
        for link in candidate_links:
            if isinstance(link, str) and link:
                return link
        return ""

    def _store_name(self, store: dict[str, object], link: str) -> str:
        candidate_names: Iterable[object] = (
            store.get("merchant"),
            store.get("seller"),
            store.get("store"),
            store.get("source"),
            store.get("name"),
        )
        for candidate in candidate_names:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return self.derive_platform_name(None, link)

    @staticmethod
    def _to_float(value: object) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: object) -> int | None:
        if isinstance(value, str):
            digits_only = re.sub(r"[^\d]", "", value)
            if digits_only:
                value = digits_only
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
