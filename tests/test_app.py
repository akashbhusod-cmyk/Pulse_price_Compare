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


def test_api_routes_are_rate_limited(monkeypatch):
    client = create_test_client(monkeypatch, rate_limit=1)

    first_response = client.get("/api/search-history")
    second_response = client.get("/api/search-history")

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.get_json()["error"] == "Rate limit exceeded"
