"""
Rate limiting middleware for CanaryScope API.

Simple in-memory rate limiter. For production with multiple instances,
use Redis-backed rate limiting.
"""
import os
import time
from collections import defaultdict
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple rate limiting middleware using sliding window counter.

    For production with multiple API instances, replace with Redis-backed
    rate limiting (e.g., slowapi with Redis backend).
    """

    def __init__(self, app, requests_per_minute: int = 60):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.window_size = 60  # seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier for rate limiting."""
        # Use X-Forwarded-For if behind a proxy, otherwise use client host
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _clean_old_requests(self, client_id: str, current_time: float) -> None:
        """Remove requests outside the current window."""
        cutoff = current_time - self.window_size
        self.requests[client_id] = [
            ts for ts in self.requests[client_id] if ts > cutoff
        ]

    def _is_rate_limited(self, client_id: str) -> tuple[bool, int]:
        """Check if client is rate limited. Returns (is_limited, remaining)."""
        current_time = time.time()
        self._clean_old_requests(client_id, current_time)

        request_count = len(self.requests[client_id])
        remaining = max(0, self.requests_per_minute - request_count)

        if request_count >= self.requests_per_minute:
            return True, remaining

        self.requests[client_id].append(current_time)
        return False, remaining - 1

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks, admin endpoints, and localhost
        skip_paths = ["/health", "/", "/docs", "/redoc", "/openapi.json"]
        client_host = request.client.host if request.client else ""
        is_localhost = client_host in ["127.0.0.1", "localhost", "::1"]

        if request.url.path in skip_paths or request.url.path.startswith("/admin") or is_localhost:
            return await call_next(request)

        client_id = self._get_client_id(request)
        is_limited, remaining = self._is_rate_limited(client_id)

        if is_limited:
            # Include CORS headers in rate limit response
            origin = request.headers.get("origin", "*")
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests",
                    "message": f"Rate limit exceeded. Please wait before making more requests.",
                    "retry_after": self.window_size,
                },
                headers={
                    "X-RateLimit-Limit": str(self.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + self.window_size),
                    "Retry-After": str(self.window_size),
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                },
            )

        response = await call_next(request)

        # Add rate limit headers to response
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(int(time.time()) + self.window_size)

        return response


def get_rate_limit_middleware(app) -> RateLimitMiddleware:
    """Factory function to create rate limit middleware with env config."""
    requests_per_minute = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))
    return RateLimitMiddleware(app, requests_per_minute=requests_per_minute)
