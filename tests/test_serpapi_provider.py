from __future__ import annotations

from pricepulse_compare.models import Offer
from pricepulse_compare.services.providers.serpapi_provider import SerpApiProvider
from pricepulse_compare.settings import AppSettings


def test_matching_offers_requires_model_token_and_rejects_variant_mismatches():
    provider = SerpApiProvider(AppSettings())
    query = "Samsung Galaxy S24"

    exact_match = Offer(
        title="Samsung Galaxy S24 5G 256GB",
        source="Amazon",
        platform="Amazon",
        price=64999,
        currency="INR",
        product_url="https://amazon.in/s24",
    )
    variant_plus = Offer(
        title="Samsung Galaxy S24+ 256GB",
        source="Amazon",
        platform="Amazon",
        price=69999,
        currency="INR",
        product_url="https://amazon.in/s24-plus",
    )
    variant_ultra = Offer(
        title="Samsung Galaxy S24 Ultra 256GB",
        source="Amazon",
        platform="Amazon",
        price=109999,
        currency="INR",
        product_url="https://amazon.in/s24-ultra",
    )
    wrong_model = Offer(
        title="Samsung Galaxy S23 256GB",
        source="Amazon",
        platform="Amazon",
        price=54999,
        currency="INR",
        product_url="https://amazon.in/s23",
    )
    accessory = Offer(
        title="Samsung Galaxy S24 Case Cover",
        source="Amazon",
        platform="Amazon",
        price=499,
        currency="INR",
        product_url="https://amazon.in/s24-case",
    )

    matched = provider._matching_offers(
        query,
        [variant_plus, variant_ultra, wrong_model, accessory, exact_match],
        strict=True,
    )

    assert matched == [exact_match]
