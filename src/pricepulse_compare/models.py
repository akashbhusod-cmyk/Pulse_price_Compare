from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class Offer:
    title: str
    source: str
    platform: str
    price: float
    currency: str
    product_url: str
    image_url: str | None = None
    old_price: float | None = None
    rating: float | None = None
    reviews: int | None = None
    delivery: str | None = None
    provider: str = "demo"
    source_type: str = "demo"

    @property
    def savings_amount(self) -> float:
        if self.old_price and self.old_price > self.price:
            return round(self.old_price - self.price, 2)
        return 0.0

    @property
    def savings_percent(self) -> float:
        if self.old_price and self.old_price > self.price:
            return round(((self.old_price - self.price) / self.old_price) * 100, 2)
        return 0.0

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["savings_amount"] = self.savings_amount
        payload["savings_percent"] = self.savings_percent
        return payload


@dataclass(slots=True)
class ProviderResult:
    provider: str
    offers: list[Offer] = field(default_factory=list)
    live: bool = False
    message: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "offers": [offer.to_dict() for offer in self.offers],
            "live": self.live,
            "message": self.message,
            "error": self.error,
        }
