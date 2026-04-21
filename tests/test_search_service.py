from __future__ import annotations

from pricepulse_compare.models import Offer
from pricepulse_compare.services.search_service import SearchService


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
