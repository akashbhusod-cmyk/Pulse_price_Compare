from __future__ import annotations

import re
from statistics import mean
from urllib.parse import quote_plus

from pricepulse_compare.models import Offer, ProviderResult
from pricepulse_compare.services.providers.dataforseo_provider import DataForSeoProvider
from pricepulse_compare.services.providers.demo_provider import DemoProvider
from pricepulse_compare.services.providers.serpapi_provider import SerpApiProvider
from pricepulse_compare.settings import AppSettings


class SearchService:
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

    def _build_providers(self) -> list[object]:
        registry = {
            "demo": DemoProvider(self.settings),
            "serpapi": SerpApiProvider(self.settings),
            "dataforseo": DataForSeoProvider(self.settings),
        }
        providers = []
        for name in self.settings.provider_names:
            if name == "demo" and not self.settings.enable_demo_fallback:
                continue
            if name in registry:
                providers.append(registry[name])
        return providers

    def search(self, query: str) -> dict[str, object]:
        provider_results = [self._run_provider(provider, query) for provider in self.providers]
        all_offers = self._deduplicate(
            [offer for provider_result in provider_results for offer in provider_result.offers]
        )

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

        if not live_results:
            if "serpapi" in self.settings.provider_names and not self.settings.serpapi_key:
                live_required_message = (
                    "Live pricing is disabled because SERPAPI_KEY is missing in .env. "
                    "Add your SerpApi key and restart the server."
                )
            elif not provider_results:
                live_required_message = (
                    "No active providers are configured. Enable SerpApi or DataForSEO in .env."
                )
            else:
                live_required_message = (
                    "No live marketplace listings were returned for this query. "
                    "Try another product name or check your provider configuration."
                )

        return {
            "query": query,
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
            "live_required_message": live_required_message,
            "search_suggestions": search_suggestions,
            "popular_platform_searches": self._build_popular_platform_searches(query),
        }

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
                    f"{provider_name} failed while processing the live response. "
                    "The app kept running and skipped that provider for this search."
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
