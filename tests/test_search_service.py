from __future__ import annotations

from pricepulse_compare.models import Offer
from pricepulse_compare.settings import AppSettings
from pricepulse_compare.services.providers.demo_provider import DemoProvider
from pricepulse_compare.services.search_service import ParsedQuery, SearchService


def test_deduplicate_keeps_unique_platform_price_combinations():
    duplicate = Offer(
        title="iPhone 15",
        source="Amazon",
        platform="Amazon",
        price=64999,
        currency="INR",
        product_url="https://example.com/one",
    )
    same_offer = Offer(
        title=" iPhone 15 ",
        source="Amazon",
        platform="amazon",
        price=64999.004,
        currency="INR",
        product_url="https://example.com/two",
    )
    different_platform = Offer(
        title="iPhone 15",
        source="Flipkart",
        platform="Flipkart",
        price=64999,
        currency="INR",
        product_url="https://example.com/three",
    )

    unique = SearchService._deduplicate([duplicate, same_offer, different_platform])

    assert unique == [duplicate, different_platform]


def test_build_search_suggestions_for_phone_query_adds_helpful_variants():
    suggestions = SearchService._build_search_suggestions("Samsung S24", [])

    assert suggestions == [
        "Samsung S24 5G",
        "Samsung S24 smartphone",
        "Samsung S24 128GB",
    ]


def test_build_search_suggestions_returns_empty_when_offers_exist():
    offer = Offer(
        title="Samsung S24",
        source="Amazon",
        platform="Amazon",
        price=69999,
        currency="INR",
        product_url="https://example.com/s24",
    )

    assert SearchService._build_search_suggestions("Samsung S24", [offer]) == []


def test_demo_provider_extracts_budget_and_category_for_broad_query():
    context = DemoProvider._build_query_context("Best smartphone under 20000")

    assert context["categories"] == {"smartphone"}
    assert context["max_price"] == 20000.0
    assert context["tokens"] == set()


def test_demo_provider_relaxes_budget_when_catalog_has_no_budget_match():
    provider = DemoProvider(AppSettings())

    result = provider.search("Best smartphone under 20000")

    assert result.offers
    assert all(offer.provider == "demo" for offer in result.offers)
    assert all(offer.price <= 20000 for offer in result.offers)


def test_parse_natural_query_extracts_category_budget_brand_and_feature():
    parsed = SearchService._parse_natural_query("best gaming laptop under 60k with rtx from hp")

    assert parsed.category == "laptop"
    assert parsed.min_price is None
    assert parsed.max_price == 60000.0
    assert "hp" in parsed.brands
    assert "rtx" in parsed.features
    assert parsed.normalized == "gaming rtx hp laptop"
    assert parsed.provider_query == "gaming rtx hp laptop under 60000"


def test_apply_query_filters_keeps_matching_phone_budget_results():
    offers = [
        Offer(
            title="Samsung Galaxy A35 5G",
            source="Amazon",
            platform="Amazon",
            price=19999,
            currency="INR",
            product_url="https://example.com/a35",
        ),
        Offer(
            title="Dell Inspiron 15 Laptop",
            source="Amazon",
            platform="Amazon",
            price=54999,
            currency="INR",
            product_url="https://example.com/dell",
        ),
    ]
    parsed = ParsedQuery(
        original="cheap samsung phone 5g under 20000",
        normalized="samsung 5g smartphone",
        provider_query="samsung smartphone 5g under 20000",
        category="smartphone",
        min_price=None,
        max_price=20000,
        brands=["samsung"],
        features=["5g"],
        tokens=["samsung", "5g"],
    )

    filtered = SearchService._apply_query_filters(offers, parsed)

    assert filtered == [offers[0]]


def test_apply_query_filters_prefers_budget_band_over_very_cheap_results():
    offers = [
        Offer(
            title="Redmi A1",
            source="Amazon",
            platform="Amazon",
            price=5899,
            currency="INR",
            product_url="https://example.com/redmi-a1",
        ),
        Offer(
            title="Samsung Galaxy M35 5G",
            source="Amazon",
            platform="Amazon",
            price=18499,
            currency="INR",
            product_url="https://example.com/m35",
        ),
        Offer(
            title="OnePlus Nord CE 4 Lite 5G",
            source="Amazon",
            platform="Amazon",
            price=21999,
            currency="INR",
            product_url="https://example.com/nord-ce-4-lite",
        ),
    ]
    parsed = ParsedQuery(
        original="best smartphone under 20000",
        normalized="smartphone",
        provider_query="smartphone under 20000",
        category="smartphone",
        min_price=None,
        max_price=20000,
        brands=[],
        features=[],
        tokens=[],
    )

    filtered = SearchService._apply_query_filters(offers, parsed)

    assert filtered == [offers[1]]


def test_apply_query_filters_falls_back_to_closest_budget_matches():
    offers = [
        Offer(
            title="Redmi A1",
            source="Amazon",
            platform="Amazon",
            price=5899,
            currency="INR",
            product_url="https://example.com/redmi-a1",
        ),
        Offer(
            title="Moto G85 5G",
            source="Amazon",
            platform="Amazon",
            price=17999,
            currency="INR",
            product_url="https://example.com/moto-g85",
        ),
        Offer(
            title="Nothing Phone 2a",
            source="Flipkart",
            platform="Flipkart",
            price=23999,
            currency="INR",
            product_url="https://example.com/nothing-2a",
        ),
    ]
    parsed = ParsedQuery(
        original="best smartphone under 30000",
        normalized="smartphone",
        provider_query="smartphone under 30000",
        category="smartphone",
        min_price=None,
        max_price=30000,
        brands=[],
        features=[],
        tokens=[],
    )

    filtered = SearchService._apply_query_filters(offers, parsed)

    assert filtered == [offers[2], offers[1]]


def test_parse_natural_query_extracts_explicit_price_range():
    parsed = SearchService._parse_natural_query("best phone between 20000 and 30000")

    assert parsed.category == "smartphone"
    assert parsed.min_price == 20000.0
    assert parsed.max_price == 30000.0
    assert parsed.provider_query == "smartphone between 20000 and 30000"


def test_parse_natural_query_keeps_model_number_and_variant_for_exact_search():
    parsed = SearchService._parse_natural_query("iphone 17 pro")

    assert parsed.brands == ["iphone"]
    assert parsed.tokens == ["iphone", "17", "pro"]
    assert parsed.provider_query == "iphone 17 pro smartphone"
    assert parsed.has_filters is True


def test_apply_query_filters_rejects_wrong_phone_generation_for_exact_model_search():
    offers = [
        Offer(
            title="Apple iPhone 11",
            source="Cashify",
            platform="Cashify",
            price=16199,
            currency="INR",
            product_url="https://example.com/iphone-11",
        ),
        Offer(
            title="Apple iPhone 17 Pro 256GB",
            source="Amazon",
            platform="Amazon",
            price=129999,
            currency="INR",
            product_url="https://example.com/iphone-17-pro",
        ),
    ]
    parsed = ParsedQuery(
        original="iphone 17 pro",
        normalized="iphone 17 pro",
        provider_query="iphone 17 pro",
        category=None,
        min_price=None,
        max_price=None,
        brands=["iphone"],
        features=[],
        tokens=["iphone", "17", "pro"],
    )

    filtered = SearchService._apply_query_filters(offers, parsed)

    assert filtered == [offers[1]]


def test_apply_query_filters_rejects_wrong_model_family_for_token_only_search():
    offers = [
        Offer(
            title="Samsung Galaxy A35 5G",
            source="Amazon",
            platform="Amazon",
            price=28999,
            currency="INR",
            product_url="https://example.com/a35",
        ),
        Offer(
            title="Samsung Galaxy S24 Ultra 256GB",
            source="Flipkart",
            platform="Flipkart",
            price=119999,
            currency="INR",
            product_url="https://example.com/s24-ultra",
        ),
    ]
    parsed = ParsedQuery(
        original="s24 ultra",
        normalized="s24 ultra",
        provider_query="s24 ultra",
        category=None,
        min_price=None,
        max_price=None,
        brands=[],
        features=[],
        tokens=["s24", "ultra"],
    )

    filtered = SearchService._apply_query_filters(offers, parsed)

    assert filtered == [offers[1]]


def test_exact_query_tokens_keep_specific_model_words_for_non_budget_searches():
    parsed = ParsedQuery(
        original="dell inspiron 15",
        normalized="dell inspiron 15",
        provider_query="dell inspiron 15",
        category=None,
        min_price=None,
        max_price=None,
        brands=["dell"],
        features=[],
        tokens=["dell", "inspiron", "15"],
    )

    assert SearchService._exact_query_tokens(parsed) == ["inspiron", "15"]


def test_fallback_specific_product_matches_returns_closest_same_family_models():
    offers = [
        Offer(
            title="Apple iPhone 16",
            source="Cashify",
            platform="Cashify",
            price=61999,
            currency="INR",
            product_url="https://example.com/iphone-16",
        ),
        Offer(
            title="Apple iPhone 17 128GB",
            source="Flipkart",
            platform="Flipkart",
            price=87999,
            currency="INR",
            product_url="https://example.com/iphone-17",
        ),
        Offer(
            title="Apple iPhone 17 Pro Max",
            source="Amazon",
            platform="Amazon",
            price=129999,
            currency="INR",
            product_url="https://example.com/iphone-17-pro-max",
        ),
    ]
    parsed = ParsedQuery(
        original="iphone 17 pro",
        normalized="iphone 17 pro",
        provider_query="iphone 17 pro",
        category="smartphone",
        min_price=None,
        max_price=None,
        brands=["iphone"],
        features=[],
        tokens=["iphone", "17", "pro"],
    )

    fallback = SearchService._fallback_specific_product_matches(offers, parsed)

    assert [offer.title for offer in fallback] == ["Apple iPhone 17 Pro Max", "Apple iPhone 17 128GB"]


def test_related_same_generation_matches_append_close_variants_without_older_generation():
    strict_matches = [
        Offer(
            title="Apple iPhone 17 Pro 256GB",
            source="Amazon",
            platform="Amazon",
            price=119999,
            currency="INR",
            product_url="https://example.com/iphone-17-pro",
        ),
    ]
    offers = strict_matches + [
        Offer(
            title="Apple iPhone 17 Pro Max 256GB",
            source="Flipkart",
            platform="Flipkart",
            price=129999,
            currency="INR",
            product_url="https://example.com/iphone-17-pro-max",
        ),
        Offer(
            title="Apple iPhone 17 128GB",
            source="Croma",
            platform="Croma",
            price=87999,
            currency="INR",
            product_url="https://example.com/iphone-17",
        ),
        Offer(
            title="Apple iPhone 16 Pro",
            source="Cashify",
            platform="Cashify",
            price=79999,
            currency="INR",
            product_url="https://example.com/iphone-16-pro",
        ),
    ]
    parsed = ParsedQuery(
        original="iphone 17 pro",
        normalized="iphone 17 pro",
        provider_query="iphone 17 pro smartphone",
        category="smartphone",
        min_price=None,
        max_price=None,
        brands=["iphone"],
        features=[],
        tokens=["iphone", "17", "pro"],
    )

    related = SearchService._related_same_generation_matches(offers, parsed, strict_matches)

    assert [offer.title for offer in related] == [
        "Apple iPhone 17 Pro Max 256GB",
        "Apple iPhone 17 128GB",
    ]


def test_same_generation_family_query_drops_variant_but_keeps_generation():
    parsed = ParsedQuery(
        original="iphone 16 pro",
        normalized="iphone 16 pro",
        provider_query="iphone 16 pro smartphone",
        category="smartphone",
        min_price=None,
        max_price=None,
        brands=["iphone"],
        features=[],
        tokens=["iphone", "16", "pro"],
    )

    assert SearchService._same_generation_family_query(parsed) == "iphone 16 smartphone"


def test_should_fetch_family_query_skips_extra_lookup_when_same_generation_results_are_already_enough():
    parsed = ParsedQuery(
        original="iphone 16 pro",
        normalized="iphone 16 pro",
        provider_query="iphone 16 pro smartphone",
        category="smartphone",
        min_price=None,
        max_price=None,
        brands=["iphone"],
        features=[],
        tokens=["iphone", "16", "pro"],
    )
    offers = [
        Offer(
            title="Apple iPhone 16 Pro 128GB",
            source="Amazon",
            platform="Amazon",
            price=109900,
            currency="INR",
            product_url="https://example.com/iphone-16-pro",
        ),
        Offer(
            title="Apple iPhone 16 Pro Max 256GB",
            source="Flipkart",
            platform="Flipkart",
            price=139900,
            currency="INR",
            product_url="https://example.com/iphone-16-pro-max",
        ),
        Offer(
            title="Apple iPhone 16 128GB",
            source="Croma",
            platform="Croma",
            price=79900,
            currency="INR",
            product_url="https://example.com/iphone-16",
        ),
    ]

    assert SearchService._should_fetch_family_query(parsed, offers) is False


def test_build_providers_skips_unconfigured_live_services():
    settings = AppSettings(
        provider_names=["serpapi", "dataforseo", "demo"],
        serpapi_key="",
        dataforseo_login="",
        dataforseo_password="",
        enable_demo_fallback=True,
    )

    service = SearchService(settings)

    assert [provider.provider_name for provider in service.providers] == ["demo"]
