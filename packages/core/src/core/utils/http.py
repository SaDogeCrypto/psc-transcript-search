"""
HTTP client utilities with retry and rate limiting.
"""

import time
import logging
from typing import Optional, Dict, Any
from functools import wraps

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


def create_client(
    timeout: float = 30.0,
    headers: Optional[Dict[str, str]] = None,
    verify_ssl: bool = True,
) -> httpx.Client:
    """Create an HTTP client with common settings."""
    default_headers = {
        'User-Agent': 'CanaryScope Research Bot (contact: admin@canaryscope.com)'
    }
    if headers:
        default_headers.update(headers)

    return httpx.Client(
        timeout=timeout,
        headers=default_headers,
        verify=verify_ssl,
        follow_redirects=True,
    )


def create_async_client(
    timeout: float = 30.0,
    headers: Optional[Dict[str, str]] = None,
    verify_ssl: bool = True,
) -> httpx.AsyncClient:
    """Create an async HTTP client with common settings."""
    default_headers = {
        'User-Agent': 'CanaryScope Research Bot (contact: admin@canaryscope.com)'
    }
    if headers:
        default_headers.update(headers)

    return httpx.AsyncClient(
        timeout=timeout,
        headers=default_headers,
        verify=verify_ssl,
        follow_redirects=True,
    )


class RateLimiter:
    """Simple rate limiter for HTTP requests."""

    def __init__(self, requests_per_second: float = 1.0):
        self.min_interval = 1.0 / requests_per_second
        self.last_request_time = 0.0

    def wait(self):
        """Wait if necessary to maintain rate limit."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()

    async def wait_async(self):
        """Async wait if necessary to maintain rate limit."""
        import asyncio
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_interval:
            await asyncio.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()


def with_retry(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
):
    """
    Decorator for retrying HTTP operations with exponential backoff.

    Usage:
        @with_retry(max_attempts=3)
        def fetch_data(url):
            return httpx.get(url)
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=min_wait, max=max_wait),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    )


__all__ = [
    'create_client',
    'create_async_client',
    'RateLimiter',
    'with_retry',
]
