from __future__ import annotations

from dataclasses import dataclass
import re
from statistics import mean
from urllib.parse import quote_plus
from copy import deepcopy

from pricepulse_compare.models import Offer, ProviderResult
from pricepulse_compare.services.providers.dataforseo_provider import DataForSeoProvider
from pricepulse_compare.services.providers.demo_provider import DemoProvider
from pricepulse_compare.services.providers.serpapi_provider import SerpApiProvider
from pricepulse_compare.settings import AppSettings


@dataclass(slots=True)
class ParsedQuery:
    original: str
    normalized: str
    provider_query: str
    category: str | None
    min_price: float | None
    max_price: float | None
    brands: list[str]
    features: list[str]
    tokens: list[str]

    @property
    def has_filters(self) -> bool:
        return bool(
            self.category
            or self.min_price is not None
            or self.max_price is not None
            or self.brands
            or self.features
            or self.tokens
        )

    def summary(self) -> str | None:
        parts: list[str] = []
        if self.category:
            parts.append(self.category)
        if self.brands:
            parts.append(", ".join(self.brands))
        if self.features:
            parts.append(", ".join(self.features))
        if self.min_price is not None and self.max_price is not None:
            parts.append(f"Rs. {self.min_price:,.0f} to Rs. {self.max_price:,.0f}")
        elif self.min_price is not None:
            parts.append(f"above Rs. {self.min_price:,.0f}")
        if self.max_price is not None:
            if self.min_price is None:
                parts.append(f"under Rs. {self.max_price:,.0f}")
        if not parts:
            return None
        return "Interpreted as " + " | ".join(parts)


class SearchService:
    search_cache_version = "v7"
    strict_variant_tokens = {"pro", "plus", "max", "ultra", "mini", "note", "fe", "air", "lite", "se"}
    generic_descriptor_tokens = {
        "android", "camera", "gaming", "laptop", "mobile", "phone", "smartphone",
        "tablet", "tv", "watch", "wireless",
    }
    stop_words = {
        "a", "an", "and", "best", "below", "buy", "cheap", "compare", "deals",
        "find", "for", "from", "good", "in", "latest", "less", "me", "near", "of",
        "on", "price", "products", "search", "show", "than", "the", "to",
        "top", "under", "upto", "up", "with",
    }
    category_aliases = {
        "smartphone": {"5g phone", "mobile", "mobile phone", "phone", "smartphone", "smartphones"},
        "laptop": {"gaming laptop", "laptop", "laptops", "notebook", "ultrabook"},
        "tv": {"oled", "qled", "smart tv", "television", "tv"},
        "audio": {"audio", "earbuds", "headphone", "headphones", "speaker"},
        "shoes": {"running shoes", "shoe", "shoes", "sneaker", "sneakers"},
    }
    known_brands = {
        "acer", "apple", "asus", "boat", "canon", "dell", "hp", "iphone", "iqoo",
        "jbl", "lenovo", "lg", "macbook", "mi", "motorola", "nike", "nikon",
        "nothing", "oneplus", "oppo", "pixel", "poco", "realme", "redmi",
        "samsung", "sony", "vivo", "xiaomi",
    }
    feature_aliases = {
        "5g": {"5g"},
        "rtx": {"rtx"},
        "oled": {"oled"},
        "qled": {"qled"},
        "128gb": {"128gb", "128 gb"},
        "256gb": {"256gb", "256 gb"},
        "512gb": {"512gb", "512 gb"},
        "ryzen 7": {"ryzen 7"},
        "i7": {"i7", "core i7"},
    }
    budget_pattern = re.compile(
        r"(?:(?:under|below|less than|max|max\.|upto|up to)\s*₹?\s*([0-9]+(?:,[0-9]+)*)(k)?)|(?:₹\s*([0-9]+(?:,[0-9]+)*))",
        re.IGNORECASE,
    )
    general_platforms = [
        ("Amazon", "https://www.amazon.in/s?k={query}"),
        ("Flipkart", "https://www.flipkart.com/search?q={query}"),
        ("Croma", "https://www.croma.com/searchB?q={query}"),
        ("Reliance Digital", "https://www.reliancedigital.in/search?q={query}"),
        ("JioMart", "https://www.jiomart.com/search/{query}"),
        ("Vijay Sales", "https://www.vijaysales.com/search/{query}"),
        ("Tata CLiQ", "https://www.tatacliq.com/search/?searchCategory=all&text={query}"),
    ]
    brand_store_platforms = [
        ({"apple", "iphone", "ipad", "macbook", "airpods"}, "Apple Store", "https://www.apple.com/in/search/{query}"),
        ({"samsung", "galaxy"}, "Samsung", "https://www.samsung.com/in/search/?searchvalue={query}"),
        ({"xiaomi", "redmi", "poco", "mi"}, "Mi.com", "https://www.mi.com/in/search/{query}/"),
        ({"oneplus"}, "OnePlus", "https://www.oneplus.in/search?keyword={query}"),
        ({"vivo"}, "Vivo", "https://www.vivo.com/in/search?q={query}"),
        ({"oppo"}, "OPPO", "https://www.oppo.com/in/search/?params={query}"),
        ({"realme"}, "realme", "https://www.realme.com/in/search?keyword={query}"),
        ({"nothing"}, "Nothing", "https://in.nothing.tech/pages/search-results-page?q={query}"),
        ({"motorola", "moto"}, "Motorola", "https://www.motorola.in/search?q={query}"),
        ({"google", "pixel"}, "Google Store", "https://store.google.com/in/search?q={query}"),
        ({"sony", "playstation", "bravia"}, "Sony", "https://www.sony.co.in/search?keyword={query}"),
        ({"lg"}, "LG", "https://www.lg.com/in/search/?search={query}"),
        ({"hp", "pavilion", "omen"}, "HP", "https://www.hp.com/in-en/shop/catalogsearch/result/?q={query}"),
        ({"dell", "alienware", "inspiron", "xps"}, "Dell", "https://www.dell.com/en-in/search/{query}"),
        ({"lenovo", "thinkpad", "ideapad"}, "Lenovo", "https://www.lenovo.com/in/en/search?text={query}"),
        ({"asus", "rog", "zenbook", "vivobook"}, "ASUS", "https://www.asus.com/in/searchresult?searchType=products&searchKey={query}"),
        ({"acer", "predator"}, "Acer", "https://store.acer.com/en-in/catalogsearch/result/?q={query}"),
        ({"boat", "airdopes"}, "boAt", "https://www.boat-lifestyle.com/search?q={query}"),
        ({"jbl"}, "JBL", "https://www.jbl.com/search?q={query}"),
        ({"canon", "eos", "pixma"}, "Canon", "https://in.canon/en/search?q={query}"),
        ({"nikon"}, "Nikon", "https://www.nikon.co.in/search?q={query}"),
    ]

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.providers = self._build_providers()
        self._search_cache: dict[str, dict[str, object]] = {}

    def _build_providers(self) -> list[object]:
        registry: dict[str, object] = {}
        if self.settings.enable_demo_fallback:
            registry["demo"] = DemoProvider(self.settings)
        if self.settings.serpapi_key:
            registry["serpapi"] = SerpApiProvider(self.settings)
        if self.settings.dataforseo_login and self.settings.dataforseo_password:
            registry["dataforseo"] = DataForSeoProvider(self.settings)
        providers = []
        for name in self.settings.provider_names:
            if name in registry:
                providers.append(registry[name])
        return providers

    def search(self, query: str) -> dict[str, object]:
        cache_key = f"{self.search_cache_version}:{' '.join(query.lower().split())}"
        cached = self._search_cache.get(cache_key)
        if cached is not None:
            return deepcopy(cached)

        parsed_query = self._parse_natural_query(query)
        provider_query = parsed_query.provider_query or parsed_query.normalized or query
        provider_results = [self._run_provider(provider, provider_query) for provider in self.providers]
        initial_offers = self._deduplicate(
            [offer for provider_result in provider_results for offer in provider_result.offers]
        )
        family_query = self._same_generation_family_query(parsed_query)
        if family_query and family_query != provider_query and self._should_fetch_family_query(parsed_query, initial_offers):
            family_results = [self._run_provider(provider, family_query) for provider in self.providers]
            provider_results.extend(family_results)
        all_offers = self._deduplicate(
            [offer for provider_result in provider_results for offer in provider_result.offers]
        )
        unfiltered_offers = all_offers
        filtered_offers = self._apply_query_filters(all_offers, parsed_query)
        fallback_message = None
        if parsed_query.has_filters:
            if filtered_offers:
                all_offers = filtered_offers
                related_offers = self._related_same_generation_matches(unfiltered_offers, parsed_query, filtered_offers)
                if related_offers:
                    all_offers = self._deduplicate(filtered_offers + related_offers)
            else:
                fallback_offers = self._fallback_specific_product_matches(unfiltered_offers, parsed_query)
                if fallback_offers:
                    all_offers = fallback_offers
                    fallback_message = (
                        f"We found the closest available matches for '{query}' so you can keep comparing right away."
                    )
                else:
                    all_offers = []

        by_price = sorted(all_offers, key=lambda offer: offer.price)
        by_savings = sorted(
            all_offers,
            key=lambda offer: (offer.savings_amount, -offer.price),
            reverse=True,
        )

        cheapest_offer = by_price[0] if by_price else None
        biggest_savings_offer = by_savings[0] if by_savings and by_savings[0].savings_amount > 0 else None
        live_results = [result for result in provider_results if result.live and result.offers]
        platform_count = len({offer.platform.lower() for offer in all_offers})
        live_required_message = None
        search_suggestions = self._build_search_suggestions(query, all_offers)
        no_discount_message = None

        if all_offers and not biggest_savings_offer:
            no_discount_message = (
                "Current price snapshots are ready now, and savings highlights will appear automatically whenever providers share discount metadata."
            )

        if not live_results:
            if "serpapi" in self.settings.provider_names and not self.settings.serpapi_key:
                live_required_message = (
                    "Sample results are ready now. Add your SerpApi key in .env anytime to unlock live marketplace pricing too."
                )
            elif not provider_results:
                live_required_message = (
                    "You can connect a live provider in .env whenever you want to expand these results with marketplace pricing."
                )
            else:
                live_required_message = (
                    "These results are ready to explore. Connect a live provider anytime if you want even broader marketplace coverage."
                )

        result = {
            "query": query,
            "interpreted_query": parsed_query.summary(),
            "search_query": provider_query,
            "summary": {
                "total_offers": len(all_offers),
                "platform_count": platform_count,
                "provider_count": len(provider_results),
                "live_provider_count": len(live_results),
                "lowest_price": cheapest_offer.price if cheapest_offer else None,
                "highest_price": max((offer.price for offer in all_offers), default=None),
                "average_price": round(mean(offer.price for offer in all_offers), 2) if all_offers else None,
            },
            "highlights": {
                "cheapest": cheapest_offer.to_dict() if cheapest_offer else None,
                "highest_savings": biggest_savings_offer.to_dict() if biggest_savings_offer else None,
            },
            "offers_by_price": [offer.to_dict() for offer in by_price],
            "offers_by_savings": [offer.to_dict() for offer in by_savings if offer.savings_amount > 0],
            "platform_table": self._build_platform_table(by_price),
            "provider_results": [result.to_dict() for result in provider_results],
            "used_demo_fallback": bool(
                self.settings.enable_demo_fallback
                and not live_results
                and any(result.provider == "demo" for result in provider_results)
            ),
            "fallback_message": fallback_message,
            "no_discount_message": no_discount_message,
            "live_required_message": live_required_message,
            "search_suggestions": search_suggestions,
            "popular_platform_searches": self._build_popular_platform_searches(query),
        }
        self._search_cache[cache_key] = deepcopy(result)
        if len(self._search_cache) > 64:
            oldest_key = next(iter(self._search_cache))
            del self._search_cache[oldest_key]
        return result

    @staticmethod
    def _run_provider(provider: object, query: str) -> ProviderResult:
        try:
            return provider.search(query)
        except Exception as exc:
            provider_name = getattr(provider, "provider_name", provider.__class__.__name__.lower())
            is_live_provider = provider_name != "demo"
            return ProviderResult(
                provider=provider_name,
                live=is_live_provider,
                error=str(exc),
                message=(
                    f"{provider_name} is temporarily unavailable for this search, and the app kept the comparison moving with the other available results."
                ),
            )

    @staticmethod
    def _deduplicate(offers: list[Offer]) -> list[Offer]:
        seen: set[tuple[str, str, float]] = set()
        unique: list[Offer] = []
        for offer in offers:
            fingerprint = (offer.title.strip().lower(), offer.platform.strip().lower(), round(offer.price, 2))
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            unique.append(offer)
        return unique

    @staticmethod
    def _build_platform_table(offers: list[Offer]) -> list[dict[str, object]]:
        table = []
        for offer in offers:
            table.append(
                {
                    "platform": offer.platform,
                    "title": offer.title,
                    "price": offer.price,
                    "old_price": offer.old_price,
                    "savings_amount": offer.savings_amount,
                    "savings_percent": offer.savings_percent,
                    "delivery": offer.delivery,
                    "product_url": offer.product_url,
                    "provider": offer.provider,
                    "source_type": offer.source_type,
                }
            )
        return table

    @staticmethod
    def _build_search_suggestions(query: str, offers: list[Offer]) -> list[str]:
        if offers:
            return []

        normalized = " ".join(query.split()).strip()
        lower = normalized.lower()
        suggestions: list[str] = []

        phone_brands = {
            "iphone", "samsung", "vivo", "oppo", "oneplus", "xiaomi",
            "realme", "iqoo", "pixel", "motorola", "redmi", "nothing",
        }

        if any(brand in lower for brand in phone_brands):
            if "5g" not in lower:
                suggestions.append(f"{normalized} 5G")
            suggestions.append(f"{normalized} smartphone")
            suggestions.append(f"{normalized} 128GB")

        return suggestions[:3]

    @classmethod
    def _build_popular_platform_searches(cls, query: str) -> list[dict[str, str]]:
        encoded = quote_plus(query.strip())
        if not encoded:
            return []

        query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        brand_platforms = [
            (platform, template)
            for brand_terms, platform, template in cls.brand_store_platforms
            if query_terms.intersection(brand_terms)
        ]
        platforms = brand_platforms + cls.general_platforms

        return [
            {
                "platform": platform,
                "url": template.format(query=encoded),
            }
            for platform, template in platforms
        ]

    @classmethod
    def _parse_natural_query(cls, query: str) -> ParsedQuery:
        normalized = " ".join(query.lower().split()).strip()
        category = cls._extract_category(normalized)
        min_price, max_price = cls._extract_price_bounds(normalized)
        brands = [brand for brand in sorted(cls.known_brands) if re.search(rf"\b{re.escape(brand)}\b", normalized)]
        features = [
            feature
            for feature, aliases in cls.feature_aliases.items()
            if any(alias in normalized for alias in aliases)
        ]

        raw_tokens = re.findall(r"[a-z0-9]+", normalized)
        tokens: list[str] = []
        seen: set[str] = set()
        for token in raw_tokens:
            if token in cls.stop_words:
                continue
            if token.isdigit():
                numeric_prices = {int(price) for price in (min_price, max_price) if price is not None}
                if int(token) in numeric_prices:
                    continue
            if token.endswith("k") and token[:-1].isdigit():
                continue
            if category and token == category:
                continue
            if token in seen:
                continue
            seen.add(token)
            tokens.append(token)

        normalized_query = " ".join(tokens)
        if category and category not in normalized_query:
            normalized_query = f"{normalized_query} {category}".strip()

        provider_parts: list[str] = []
        if normalized_query:
            provider_parts.append(normalized_query)
        elif brands:
            provider_parts.extend(brands)
        elif query.strip():
            provider_parts.append(query.strip())

        primary_query_part = provider_parts[0] if provider_parts else ""
        if category and category not in primary_query_part:
            provider_parts.append(category)
        if min_price is not None and max_price is not None:
            provider_parts.append(f"between {int(min_price)} and {int(max_price)}")
        elif min_price is not None:
            provider_parts.append(f"above {int(min_price)}")
        elif max_price is not None:
            provider_parts.append(f"under {int(max_price)}")
        provider_query = " ".join(provider_parts).strip()

        return ParsedQuery(
            original=query,
            normalized=normalized_query or query.strip(),
            provider_query=provider_query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            brands=brands,
            features=features,
            tokens=tokens,
        )

    @classmethod
    def _extract_category(cls, normalized_query: str) -> str | None:
        for category, aliases in cls.category_aliases.items():
            if any(alias in normalized_query for alias in aliases):
                return category
        return None

    @classmethod
    def _extract_price_bounds(cls, normalized_query: str) -> tuple[float | None, float | None]:
        range_match = re.search(
            r"(?:between|from)\s*₹?\s*([0-9]+(?:,[0-9]+)*)(k)?\s*(?:and|to|-)\s*₹?\s*([0-9]+(?:,[0-9]+)*)(k)?",
            normalized_query,
            re.IGNORECASE,
        )
        if range_match:
            lower = cls._coerce_price_value(range_match.group(1), bool(range_match.group(2)))
            upper = cls._coerce_price_value(range_match.group(3), bool(range_match.group(4)))
            if lower is not None and upper is not None:
                return (min(lower, upper), max(lower, upper))

        under_match = cls.budget_pattern.search(normalized_query)
        above_match = re.search(
            r"(?:above|over|more than|min|min\.|starting from)\s*₹?\s*([0-9]+(?:,[0-9]+)*)(k)?",
            normalized_query,
            re.IGNORECASE,
        )

        max_price = None
        min_price = None
        if under_match:
            max_price = cls._coerce_price_value(
                under_match.group(1) or under_match.group(3),
                bool(under_match.group(2)),
            )
        if above_match:
            min_price = cls._coerce_price_value(above_match.group(1), bool(above_match.group(2)))
        return min_price, max_price

    @staticmethod
    def _coerce_price_value(raw_number: str | None, is_thousands: bool) -> float | None:
        if not raw_number:
            return None
        try:
            value = float(raw_number.replace(",", ""))
        except ValueError:
            return None
        return value * 1000 if is_thousands else value

    @classmethod
    def _apply_query_filters(cls, offers: list[Offer], parsed_query: ParsedQuery) -> list[Offer]:
        filtered = offers

        if parsed_query.category:
            category_matches = [offer for offer in filtered if cls._offer_matches_category(offer, parsed_query.category)]
            if category_matches:
                filtered = category_matches

        if parsed_query.brands:
            brand_matches = [offer for offer in filtered if cls._offer_matches_any_term(offer, parsed_query.brands)]
            if brand_matches:
                filtered = brand_matches

        if parsed_query.features:
            feature_matches = [offer for offer in filtered if cls._offer_matches_all_terms(offer, parsed_query.features)]
            if feature_matches:
                filtered = feature_matches

        exact_tokens = cls._exact_query_tokens(parsed_query)
        if exact_tokens:
            strict_matches = [offer for offer in filtered if cls._offer_matches_all_query_tokens(offer, exact_tokens)]
            if strict_matches:
                filtered = strict_matches
            else:
                return []

        if parsed_query.min_price is not None:
            min_matches = [offer for offer in filtered if offer.price >= parsed_query.min_price]
            if min_matches:
                filtered = min_matches

        if parsed_query.max_price is not None:
            max_matches = [offer for offer in filtered if offer.price <= parsed_query.max_price]
            if max_matches:
                filtered = max_matches

        if parsed_query.min_price is not None and parsed_query.max_price is not None:
            midpoint = (parsed_query.min_price + parsed_query.max_price) / 2
            filtered = sorted(
                filtered,
                key=lambda offer: (
                    abs(offer.price - midpoint),
                    abs((offer.price - midpoint) / midpoint) if midpoint else 0,
                    offer.price,
                ),
            )
        elif parsed_query.max_price is not None:
            filtered = sorted(
                filtered,
                key=lambda offer: (
                    parsed_query.max_price - offer.price,
                    -offer.price,
                ),
            )
        elif parsed_query.min_price is not None:
            filtered = sorted(filtered, key=lambda offer: (offer.price - parsed_query.min_price, offer.price))

        return filtered

    @classmethod
    def _fallback_specific_product_matches(cls, offers: list[Offer], parsed_query: ParsedQuery) -> list[Offer]:
        exact_tokens = cls._exact_query_tokens(parsed_query)
        if not exact_tokens:
            return []

        candidates = offers
        if parsed_query.category:
            category_matches = [offer for offer in candidates if cls._offer_matches_category(offer, parsed_query.category)]
            if category_matches:
                candidates = category_matches

        if parsed_query.brands:
            brand_matches = [offer for offer in candidates if cls._offer_matches_any_term(offer, parsed_query.brands)]
            if brand_matches:
                candidates = brand_matches
            else:
                return []

        if parsed_query.features:
            feature_matches = [offer for offer in candidates if cls._offer_matches_all_terms(offer, parsed_query.features)]
            if feature_matches:
                candidates = feature_matches

        if parsed_query.min_price is not None:
            min_matches = [offer for offer in candidates if offer.price >= parsed_query.min_price]
            if min_matches:
                candidates = min_matches

        if parsed_query.max_price is not None:
            max_matches = [offer for offer in candidates if offer.price <= parsed_query.max_price]
            if max_matches:
                candidates = max_matches

        scored_candidates: list[tuple[tuple[float, float, int, float], Offer]] = []
        for offer in candidates:
            score = cls._fallback_similarity_score(offer, exact_tokens)
            if score is None:
                continue
            scored_candidates.append((score, offer))

        scored_candidates.sort(key=lambda item: item[0])
        return [offer for _, offer in scored_candidates[: min(len(scored_candidates), 8)]]

    @classmethod
    def _same_generation_family_query(cls, parsed_query: ParsedQuery) -> str | None:
        exact_tokens = cls._exact_query_tokens(parsed_query)
        numeric_tokens = [token for token in exact_tokens if any(char.isdigit() for char in token)]
        if not numeric_tokens:
            return None

        family_tokens: list[str] = []
        if parsed_query.brands:
            family_tokens.extend(parsed_query.brands)
        family_tokens.extend(numeric_tokens)

        family_query = " ".join(family_tokens).strip()
        if parsed_query.category and parsed_query.category not in family_query:
            family_query = f"{family_query} {parsed_query.category}".strip()
        return family_query or None

    @classmethod
    def _should_fetch_family_query(cls, parsed_query: ParsedQuery, offers: list[Offer]) -> bool:
        exact_tokens = cls._exact_query_tokens(parsed_query)
        if not any(any(char.isdigit() for char in token) for token in exact_tokens):
            return False

        strict_matches = cls._apply_query_filters(offers, parsed_query)
        related_matches = cls._related_same_generation_matches(offers, parsed_query, strict_matches)
        same_generation_count = len(cls._deduplicate(strict_matches + related_matches))
        return same_generation_count < 3

    @classmethod
    def _related_same_generation_matches(
        cls,
        offers: list[Offer],
        parsed_query: ParsedQuery,
        strict_matches: list[Offer],
    ) -> list[Offer]:
        exact_tokens = cls._exact_query_tokens(parsed_query)
        if not exact_tokens or not any(any(char.isdigit() for char in token) for token in exact_tokens):
            return []

        strict_fingerprints = {
            (offer.title.strip().lower(), offer.platform.strip().lower(), round(offer.price, 2))
            for offer in strict_matches
        }
        related_candidates = cls._fallback_specific_product_matches(offers, parsed_query)
        related_offers: list[Offer] = []
        for offer in related_candidates:
            fingerprint = (offer.title.strip().lower(), offer.platform.strip().lower(), round(offer.price, 2))
            if fingerprint in strict_fingerprints:
                continue
            related_offers.append(offer)
        return related_offers

    @classmethod
    def _offer_matches_category(cls, offer: Offer, category: str) -> bool:
        haystack = f"{offer.title} {offer.platform} {offer.source}".lower()
        aliases = cls.category_aliases.get(category, {category})
        if any(alias in haystack for alias in aliases.union({category})):
            return True

        if category == "smartphone":
            phone_terms = {
                "apple", "galaxy", "iphone", "mobile", "oneplus", "oppo", "phone",
                "pixel", "realme", "redmi", "samsung", "smartphone", "vivo", "xiaomi",
            }
            return any(term in haystack for term in phone_terms)

        if category == "laptop":
            laptop_terms = {
                "acer", "asus", "dell", "gaming laptop", "hp", "laptop", "lenovo",
                "macbook", "notebook", "ryzen", "victus",
            }
            return any(term in haystack for term in laptop_terms)

        return False

    @staticmethod
    def _offer_matches_any_term(offer: Offer, terms: list[str]) -> bool:
        haystack = f"{offer.title} {offer.platform} {offer.source}".lower()
        return any(term in haystack for term in terms)

    @staticmethod
    def _offer_matches_all_terms(offer: Offer, terms: list[str]) -> bool:
        haystack = f"{offer.title} {offer.platform} {offer.source}".lower()
        return all(term in haystack for term in terms)

    @classmethod
    def _exact_query_tokens(cls, parsed_query: ParsedQuery) -> list[str]:
        brand_tokens = set(parsed_query.brands)
        feature_tokens = {feature.lower() for feature in parsed_query.features}
        exact_tokens: list[str] = []
        should_require_specific_terms = (
            parsed_query.min_price is None
            and parsed_query.max_price is None
            and len(parsed_query.tokens) >= 2
        )
        for token in parsed_query.tokens:
            if token in brand_tokens or token in feature_tokens:
                continue
            if token.isdigit() or any(char.isdigit() for char in token) or token in cls.strict_variant_tokens:
                exact_tokens.append(token)
                continue
            if should_require_specific_terms and token not in cls.generic_descriptor_tokens:
                exact_tokens.append(token)
        return exact_tokens

    @classmethod
    def _offer_matches_all_query_tokens(cls, offer: Offer, tokens: list[str]) -> bool:
        haystack = f"{offer.title} {offer.platform} {offer.source}".lower()
        compact_haystack = re.sub(r"[^a-z0-9]+", "", haystack)
        word_tokens = set(re.findall(r"[a-z0-9]+", haystack))
        return all(cls._query_token_matches(token, haystack, compact_haystack, word_tokens) for token in tokens)

    @classmethod
    def _query_token_matches(
        cls,
        token: str,
        haystack: str,
        compact_haystack: str,
        word_tokens: set[str],
    ) -> bool:
        if token in word_tokens:
            return True
        if any(char.isdigit() for char in token):
            return token in compact_haystack
        if token in cls.strict_variant_tokens:
            return re.search(rf"\b{re.escape(token)}\b", haystack) is not None
        return token in haystack

    @classmethod
    def _fallback_similarity_score(cls, offer: Offer, exact_tokens: list[str]) -> tuple[float, float, int, float] | None:
        haystack = f"{offer.title} {offer.platform} {offer.source}".lower()
        compact_haystack = re.sub(r"[^a-z0-9]+", "", haystack)
        word_tokens = set(re.findall(r"[a-z0-9]+", haystack))

        matched_exact = 0
        numeric_penalty = 0.0
        variant_penalty = 0.0
        text_penalty = 0.0
        numeric_distance_hits = 0

        for token in exact_tokens:
            if cls._query_token_matches(token, haystack, compact_haystack, word_tokens):
                matched_exact += 1
                continue

            if any(char.isdigit() for char in token):
                return None

            if token in cls.strict_variant_tokens:
                variant_penalty += 1.0
                continue

            if token in haystack:
                matched_exact += 1
            else:
                text_penalty += 1.5

        return (
            numeric_penalty,
            variant_penalty,
            text_penalty,
            -matched_exact,
            offer.price,
        )
