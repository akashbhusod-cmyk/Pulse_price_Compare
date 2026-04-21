from __future__ import annotations

import time

import requests
from requests.auth import HTTPBasicAuth

from pricepulse_compare.models import Offer, ProviderResult
from pricepulse_compare.services.providers.base import SearchProvider
from pricepulse_compare.settings import AppSettings


class DataForSeoProvider(SearchProvider):
    provider_name = "dataforseo"
    task_post_url = "https://api.dataforseo.com/v3/merchant/google/products/task_post"
    task_get_url = "https://api.dataforseo.com/v3/merchant/google/products/task_get/advanced/{task_id}"

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def search(self, query: str) -> ProviderResult:
        if not self.settings.dataforseo_login or not self.settings.dataforseo_password:
            return ProviderResult(
                provider=self.provider_name,
                live=False,
                message="DataForSEO credentials not configured.",
            )

        auth = HTTPBasicAuth(self.settings.dataforseo_login, self.settings.dataforseo_password)
        payload = [
            {
                "keyword": query,
                "location_name": self.settings.dataforseo_location_name,
                "language_name": self.settings.dataforseo_language_name,
                "depth": self.settings.result_limit,
                "search_param": "&tbs=p_ord:p",
            }
        ]

        try:
            post_response = requests.post(
                self.task_post_url,
                json=payload,
                auth=auth,
                timeout=self.settings.request_timeout,
            )
            post_response.raise_for_status()
            task_payload = post_response.json()
        except requests.RequestException as exc:
            return ProviderResult(
                provider=self.provider_name,
                live=True,
                error=str(exc),
                message="DataForSEO task creation failed.",
            )

        task_id = self._extract_task_id(task_payload)
        if not task_id:
            return ProviderResult(
                provider=self.provider_name,
                live=True,
                error="Missing task id in DataForSEO response.",
                message="DataForSEO returned an unexpected response.",
            )

        for _ in range(8):
            result = self._fetch_task_result(task_id, auth)
            if result is not None:
                return result
            time.sleep(1.25)

        return ProviderResult(
            provider=self.provider_name,
            live=True,
            error="Timed out while waiting for DataForSEO results.",
            message="DataForSEO task was created, but the result was not ready in time.",
        )

    def _fetch_task_result(self, task_id: str, auth: HTTPBasicAuth) -> ProviderResult | None:
        try:
            response = requests.get(
                self.task_get_url.format(task_id=task_id),
                auth=auth,
                timeout=self.settings.request_timeout,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException:
            return ProviderResult(
                provider=self.provider_name,
                live=True,
                error="Could not fetch DataForSEO task result.",
                message="DataForSEO result polling failed.",
            )

        offers = self._extract_offers(payload)
        if not offers:
            return None

        return ProviderResult(
            provider=self.provider_name,
            offers=offers,
            live=True,
            message="Live Google Shopping results from DataForSEO.",
        )

    @staticmethod
    def _extract_task_id(payload: dict[str, object]) -> str | None:
        tasks = payload.get("tasks", [])
        if not isinstance(tasks, list) or not tasks:
            return None
        task = tasks[0]
        if not isinstance(task, dict):
            return None
        return str(task.get("id")) if task.get("id") else None

    def _extract_offers(self, payload: dict[str, object]) -> list[Offer]:
        tasks = payload.get("tasks", [])
        if not isinstance(tasks, list):
            return []

        offers: list[Offer] = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            results = task.get("result", [])
            if not isinstance(results, list):
                continue

            for result in results:
                if not isinstance(result, dict):
                    continue
                items = result.get("items", [])
                if not isinstance(items, list):
                    continue

                for item in items[: self.settings.result_limit]:
                    price = self.extract_price(item.get("price"))
                    if price is None:
                        continue

                    source = item.get("domain") or self.derive_platform_name(None, item.get("shopping_url"))
                    product_images = item.get("product_images") if isinstance(item.get("product_images"), list) else []
                    rating_data = item.get("product_rating") if isinstance(item.get("product_rating"), dict) else {}
                    rating_value = rating_data.get("value")
                    votes_count = rating_data.get("votes_count")

                    offers.append(
                        Offer(
                            title=item.get("title", "Unknown product"),
                            source=source,
                            platform=source,
                            price=price,
                            old_price=self.extract_price(item.get("old_price")),
                            currency=item.get("currency", "USD"),
                            product_url=item.get("shopping_url") or "",
                            image_url=product_images[0] if product_images else None,
                            rating=self._to_float(rating_value),
                            reviews=self._to_int(votes_count),
                            delivery=(
                                item.get("delivery_info", {}).get("delivery_message")
                                if isinstance(item.get("delivery_info"), dict)
                                else None
                            ),
                            provider=self.provider_name,
                            source_type="live",
                        )
                    )

        return offers[: self.settings.result_limit]

    @staticmethod
    def _to_float(value: object) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: object) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
