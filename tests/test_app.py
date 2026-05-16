from __future__ import annotations

from pathlib import Path


TEST_DATA_DIR = Path(__file__).resolve().parent / "_tmp"


def create_test_client(monkeypatch, rate_limit: int = 60):
    monkeypatch.setenv("MYSQL_ENABLED", "false")
    monkeypatch.setenv("DATA_PROVIDERS", "demo")
    monkeypatch.setenv("ENABLE_DEMO_FALLBACK", "true")
    monkeypatch.setenv("API_RATE_LIMIT_PER_MINUTE", str(rate_limit))

    import pricepulse_compare.database as database
    from pricepulse_compare import create_app

    TEST_DATA_DIR.mkdir(exist_ok=True)
    monkeypatch.setattr(database, "DATA_DIR", TEST_DATA_DIR)
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def test_health_endpoint_reports_ok(monkeypatch):
    client = create_test_client(monkeypatch)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["database"]["enabled"] is False


def test_api_search_requires_query(monkeypatch):
    client = create_test_client(monkeypatch)

    response = client.get("/api/search")

    assert response.status_code == 400
    assert response.get_json()["error"] == "Missing query parameter q"


def test_api_search_returns_demo_results(monkeypatch):
    client = create_test_client(monkeypatch)

    response = client.get("/api/search?q=iphone")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["query"] == "iphone"
    assert payload["summary"]["total_offers"] > 0
    assert payload["used_demo_fallback"] is True
    assert payload["offers_by_price"][0]["price"] <= payload["offers_by_price"][-1]["price"]


def test_index_page_contains_loading_and_sort_controls(monkeypatch):
    client = create_test_client(monkeypatch)

    response = client.get("/?q=iphone")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "data-search-form" in html
    assert "data-search-button" in html
    assert "Sort by Price" in html
    assert "Sort by Savings" in html
    assert "Price analysis" in html
    assert "offer-analysis-data" in html
    assert "Recent searches" not in html
    assert ">History<" not in html


def test_index_page_shows_no_discount_banner_for_current_listings(monkeypatch):
    client = create_test_client(monkeypatch)

    response = client.get("/?q=iphone 17")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Recommended matches" in html
    assert "Current price snapshot" in html


def test_api_routes_are_rate_limited(monkeypatch):
    client = create_test_client(monkeypatch, rate_limit=1)

    first_response = client.get("/health")
    second_response = client.get("/health")

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.get_json()["error"] == "Rate limit exceeded"


def test_history_routes_are_not_exposed(monkeypatch):
    client = create_test_client(monkeypatch)

    history_page = client.get("/search-history")
    history_api = client.get("/api/search-history")

    assert history_page.status_code == 404
    assert history_api.status_code == 404
