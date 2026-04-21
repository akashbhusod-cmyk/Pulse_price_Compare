from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

load_dotenv(PROJECT_ROOT / ".env")


def _split_csv(raw: str) -> list[str]:
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def _clean_secret(name: str) -> str:
    value = os.getenv(name, "").strip()
    placeholders = {
        "your_key_here",
        "your_serpapi_key_here",
        "your_login_here",
        "your_password_here",
    }
    return "" if value.lower() in placeholders else value


@dataclass(slots=True)
class AppSettings:
    debug: bool = field(default_factory=lambda: os.getenv("FLASK_DEBUG", "false").lower() == "true")
    host: str = field(default_factory=lambda: os.getenv("HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "5000")))
    provider_names: list[str] = field(default_factory=lambda: _split_csv(os.getenv("DATA_PROVIDERS", "serpapi")) or ["serpapi"])
    default_location: str = field(default_factory=lambda: os.getenv("DEFAULT_LOCATION", "India"))
    default_country: str = field(default_factory=lambda: os.getenv("DEFAULT_COUNTRY", "in"))
    default_language: str = field(default_factory=lambda: os.getenv("DEFAULT_LANGUAGE", "en"))
    result_limit: int = field(default_factory=lambda: int(os.getenv("RESULT_LIMIT", "18")))
    request_timeout: int = field(default_factory=lambda: int(os.getenv("REQUEST_TIMEOUT", "20")))
    api_rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "60")))
    enable_demo_fallback: bool = field(default_factory=lambda: os.getenv("ENABLE_DEMO_FALLBACK", "false").lower() == "true")
    serpapi_key: str = field(default_factory=lambda: _clean_secret("SERPAPI_KEY"))
    serpapi_max_product_details: int = field(default_factory=lambda: int(os.getenv("SERPAPI_MAX_PRODUCT_DETAILS", "6")))
    serpapi_store_pages: int = field(default_factory=lambda: int(os.getenv("SERPAPI_STORE_PAGES", "2")))
    dataforseo_login: str = field(default_factory=lambda: _clean_secret("DATAFORSEO_LOGIN"))
    dataforseo_password: str = field(default_factory=lambda: _clean_secret("DATAFORSEO_PASSWORD"))
    dataforseo_location_name: str = field(default_factory=lambda: os.getenv("DATAFORSEO_LOCATION_NAME", "India"))
    dataforseo_language_name: str = field(default_factory=lambda: os.getenv("DATAFORSEO_LANGUAGE_NAME", "English"))
    mysql_enabled: bool = field(default_factory=lambda: os.getenv("MYSQL_ENABLED", "true").lower() == "true")
    mysql_host: str = field(default_factory=lambda: os.getenv("MYSQL_HOST", "127.0.0.1"))
    mysql_port: int = field(default_factory=lambda: int(os.getenv("MYSQL_PORT", "3306")))
    mysql_user: str = field(default_factory=lambda: os.getenv("MYSQL_USER", "root"))
    mysql_password: str = field(default_factory=lambda: os.getenv("MYSQL_PASSWORD", ""))
    mysql_database: str = field(default_factory=lambda: os.getenv("MYSQL_DATABASE", "pulse_price_compare"))
    mysql_connection_timeout: int = field(default_factory=lambda: int(os.getenv("MYSQL_CONNECTION_TIMEOUT", "3")))

    @property
    def demo_catalog_path(self) -> Path:
        return DATA_DIR / "demo_products.json"
