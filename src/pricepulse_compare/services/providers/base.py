from __future__ import annotations

import re
from abc import ABC, abstractmethod
from urllib.parse import urlparse

from pricepulse_compare.models import ProviderResult


class SearchProvider(ABC):
    provider_name = "base"

    @abstractmethod
    def search(self, query: str) -> ProviderResult:
        raise NotImplementedError

    @staticmethod
    def extract_price(value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)

        raw = str(value).strip()
        if not raw:
            return None

        cleaned = re.sub(r"[^0-9.,]", "", raw)
        if not cleaned:
            return None

        if cleaned.count(",") > 0 and cleaned.count(".") == 0:
            cleaned = cleaned.replace(",", "")
        elif cleaned.count(",") > 0 and cleaned.count(".") > 0:
            cleaned = cleaned.replace(",", "")

        try:
            return float(cleaned)
        except ValueError:
            return None

    @staticmethod
    def derive_platform_name(source: str | None, url: str | None) -> str:
        if source:
            return source.strip()
        if not url:
            return "Unknown"
        hostname = urlparse(url).netloc.replace("www.", "")
        if not hostname:
            return "Unknown"
        return hostname.split(".")[0].title()
