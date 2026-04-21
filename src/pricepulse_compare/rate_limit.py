from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque

from flask import Response, jsonify, request


class ApiRateLimiter:
    def __init__(self, limit_per_minute: int) -> None:
        self.limit = max(0, limit_per_minute)
        self.window_seconds = 60
        self._requests: dict[tuple[str, str], Deque[float]] = defaultdict(deque)

    def check(self) -> Response | None:
        if self.limit == 0 or not request.path.startswith("/api/"):
            return None

        now = time.monotonic()
        client_id = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
        key = (client_id, request.endpoint or request.path)
        timestamps = self._requests[key]

        while timestamps and now - timestamps[0] >= self.window_seconds:
            timestamps.popleft()

        if len(timestamps) >= self.limit:
            response = jsonify(
                {
                    "error": "Rate limit exceeded",
                    "message": "Too many API requests. Please wait before trying again.",
                }
            )
            response.status_code = 429
            response.headers["Retry-After"] = str(self.window_seconds)
            return response

        timestamps.append(now)
        return None
