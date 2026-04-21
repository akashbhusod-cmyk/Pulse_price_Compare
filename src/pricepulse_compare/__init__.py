from __future__ import annotations

from html import escape

from flask import Flask, Response, jsonify, render_template, request

from pricepulse_compare.database import SearchHistoryRepository
from pricepulse_compare.rate_limit import ApiRateLimiter
from pricepulse_compare.services.search_service import SearchService
from pricepulse_compare.settings import AppSettings, PROJECT_ROOT


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    settings = AppSettings()
    service = SearchService(settings)
    search_history = SearchHistoryRepository(settings)
    search_history.init_schema()
    rate_limiter = ApiRateLimiter(settings.api_rate_limit_per_minute)
    app.before_request(rate_limiter.check)

    @app.get("/")
    def index():
        query = request.args.get("q", "").strip()
        result = None
        if query:
            result = service.search(query)
            search_history.record_search(result)
        return render_template(
            "index.html",
            query=query,
            result=result,
            recent_searches=search_history.recent_searches(),
            database_status=search_history.status,
            active_providers=settings.provider_names,
            default_location=settings.default_location,
            demo_enabled=settings.enable_demo_fallback,
        )

    @app.get("/search-history")
    def search_history_page():
        return render_template(
            "history.html",
            searches=search_history.recent_searches(limit=100),
            database_status=search_history.status,
        )

    @app.get("/api/search")
    def api_search():
        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"error": "Missing query parameter q"}), 400
        result = service.search(query)
        search_history.record_search(result)
        return jsonify(result)

    @app.get("/api/search-history")
    def api_search_history():
        return jsonify(
            {
                "database": {
                    "enabled": search_history.status.enabled,
                    "available": search_history.status.available,
                    "message": search_history.status.message,
                },
                "searches": search_history.recent_searches(limit=100),
            }
        )

    @app.get("/health")
    def health():
        return jsonify(
            {
                "status": "ok",
                "providers": settings.provider_names,
                "default_location": settings.default_location,
                "database": {
                    "enabled": search_history.status.enabled,
                    "available": search_history.status.available,
                    "message": search_history.status.message,
                },
            }
        )

    @app.get("/placeholder-image")
    def placeholder_image():
        title = request.args.get("title", "Product").strip()[:48] or "Product"
        platform = request.args.get("platform", "Pulse Price").strip()[:24] or "Pulse Price"
        safe_title = escape(title)
        safe_platform = escape(platform)
        svg = f"""
<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#f6ede2"/>
      <stop offset="100%" stop-color="#f0d7bf"/>
    </linearGradient>
  </defs>
  <rect width="640" height="480" fill="url(#bg)"/>
  <rect x="40" y="40" width="560" height="400" rx="32" fill="rgba(255,255,255,0.72)"/>
  <circle cx="170" cy="210" r="74" fill="#bf5b2c" opacity="0.18"/>
  <circle cx="470" cy="146" r="52" fill="#0f766e" opacity="0.18"/>
  <text x="80" y="170" font-family="Arial, sans-serif" font-size="24" fill="#8f3f18">{safe_platform}</text>
  <text x="80" y="245" font-family="Arial, sans-serif" font-size="36" font-weight="700" fill="#182022">{safe_title}</text>
  <text x="80" y="300" font-family="Arial, sans-serif" font-size="22" fill="#5f6b6c">Live listing image not provided by API</text>
</svg>
""".strip()
        return Response(svg, mimetype="image/svg+xml")

    return app
