"""Simple in-memory rate limiter middleware.

Uses a sliding window approach per (user_id or IP) + route category.
For production, replace with Redis-backed implementation.
"""

import time
from collections import defaultdict
from typing import Optional

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.security import decode_access_token


# Rate limit config: route_prefix -> (max_requests, window_seconds)
RATE_LIMITS: dict[str, tuple[int, int]] = {
    "/api/v1/auth": (10, 60),        # 10 req/min
    "/api/v1/generate": (10, 60),    # 10 req/min (POST only, GET is excluded below)
    "/api/v1/refine": (10, 60),      # 10 req/min
    "/api/v1/edit": (10, 60),        # 10 req/min
    "/api/v1/references/upload": (10, 60),  # 10 req/min
    "/api/v1/admin": (120, 60),      # 120 req/min
    "_default": (120, 60),           # 120 req/min for all other endpoints (including polling)
}

# In-memory store: key -> list of timestamps
_request_log: dict[str, list[float]] = defaultdict(list)


def _get_rate_limit(path: str, method: str) -> tuple[int, int]:
    """Get rate limit for a given path."""
    # Only rate-limit POST for generate (GET /stream etc should be unrestricted)
    if path.startswith("/api/v1/generate") and method != "POST":
        return RATE_LIMITS["_default"]

    for prefix, limits in RATE_LIMITS.items():
        if prefix != "_default" and path.startswith(prefix):
            return limits
    return RATE_LIMITS["_default"]


def _get_client_key(request: Request) -> str:
    """Get a unique key for rate limiting: user_id if authenticated, else IP."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        payload = decode_access_token(token)
        if payload and payload.get("sub"):
            return f"user:{payload['sub']}"
    # Fallback to IP
    client_ip = request.client.host if request.client else "unknown"
    return f"ip:{client_ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        # Skip non-API routes, health checks, and SSE streams
        if not path.startswith("/api/") or path == "/api/health":
            return await call_next(request)
        if "/stream" in path:
            return await call_next(request)

        max_requests, window = _get_rate_limit(path, method)
        client_key = _get_client_key(request)
        bucket_key = f"{client_key}:{path.split('/')[3] if len(path.split('/')) > 3 else 'root'}"

        now = time.time()
        # Clean old entries for this bucket
        _request_log[bucket_key] = [
            t for t in _request_log[bucket_key] if t > now - window
        ]

        # Periodically purge empty bucket keys to prevent memory growth
        if len(_request_log) > 1000:
            stale_keys = [k for k, v in _request_log.items() if not v]
            for k in stale_keys:
                del _request_log[k]

        if len(_request_log[bucket_key]) >= max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，请在 {window} 秒后重试",
            )

        _request_log[bucket_key].append(now)
        return await call_next(request)
