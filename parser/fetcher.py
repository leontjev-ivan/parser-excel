"""HTTP loading with a global rate limit, bounded parallelism and retries."""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

import httpx

log = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

Sleep = Callable[[float], Awaitable[None]]


class FetchError(Exception):
    """The page could not be loaded even after retries."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"{reason} ({url})")
        self.url = url
        self.reason = reason


class RateLimiter:
    """Lets requests start no more often than once per `interval` seconds, across all tasks."""

    def __init__(
        self,
        interval: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._interval = interval
        self._clock = clock
        self._sleep = sleep
        self._next_start = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = self._clock()
            if self._next_start > now:
                await self._sleep(self._next_start - now)
            self._next_start = max(now, self._next_start) + self._interval


class Fetcher:
    """GET pages as text. Network errors and HTTP 429/5xx are retried with a growing pause."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        delay: float,
        concurrency: int,
        retries: int,
        retry_pause: float,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._client = client
        self._limiter = RateLimiter(delay, sleep=sleep)
        self._slots = asyncio.Semaphore(concurrency)
        self._retries = retries
        self._retry_pause = retry_pause
        self._sleep = sleep
        self.requests = 0
        self.retries_done = 0

    async def get_text(self, url: str) -> str:
        async with self._slots:
            reason = ""
            for attempt in range(self._retries + 1):
                await self._limiter.wait()
                self.requests += 1
                started = time.monotonic()
                try:
                    response = await self._client.get(url)
                except httpx.TransportError as exc:
                    reason = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
                    pause = self._pause(attempt)
                else:
                    elapsed = time.monotonic() - started
                    log.info("GET %s -> %s in %.2fs", url, response.status_code, elapsed)
                    if response.status_code == 200:
                        # the site sends "text/html" without charset; pages are UTF-8 (meta tag)
                        return response.content.decode("utf-8", errors="replace")
                    reason = f"HTTP {response.status_code}"
                    if response.status_code not in RETRY_STATUSES:
                        raise FetchError(url, reason)
                    pause = max(self._pause(attempt), _retry_after(response))
                if attempt < self._retries:
                    self.retries_done += 1
                    log.warning(
                        "retry %d/%d in %.1fs for %s: %s", attempt + 1, self._retries, pause, url, reason
                    )
                    await self._sleep(pause)
            log.error("giving up on %s after %d attempts: %s", url, self._retries + 1, reason)
            raise FetchError(url, reason)

    def _pause(self, attempt: int) -> float:
        return self._retry_pause * 2**attempt


def _retry_after(response: httpx.Response) -> float:
    value = response.headers.get("Retry-After", "")
    return float(value) if value.isdigit() else 0.0
