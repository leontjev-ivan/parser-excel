import asyncio

import httpx
import pytest

from parser.fetcher import Fetcher, FetchError, RateLimiter


class Recorder:
    """Fake asyncio.sleep: remembers pauses instead of waiting."""

    def __init__(self):
        self.pauses: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.pauses.append(seconds)


def fetch(responses, *, retries=2, retry_pause=1.0):
    """Run Fetcher.get_text against a scripted sequence of responses/exceptions."""
    calls = []
    script = iter(responses)

    def handler(request):
        calls.append(request)
        item = next(script)
        if isinstance(item, Exception):
            raise item
        return item

    sleep = Recorder()

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = Fetcher(client, delay=0, concurrency=1, retries=retries, retry_pause=retry_pause, sleep=sleep)
            return await fetcher.get_text("https://books.toscrape.com/x.html")

    return run, calls, sleep


def test_retries_server_errors_with_growing_pause():
    run, calls, sleep = fetch([httpx.Response(503), httpx.Response(502), httpx.Response(200, text="ok")])

    assert asyncio.run(run()) == "ok"
    assert len(calls) == 3
    assert sleep.pauses == [1.0, 2.0]


def test_network_error_is_retried_then_reported():
    run, calls, sleep = fetch([httpx.ConnectError("refused")] * 3)

    with pytest.raises(FetchError, match="ConnectError"):
        asyncio.run(run())
    assert len(calls) == 3  # first attempt + 2 retries
    assert sleep.pauses == [1.0, 2.0]


def test_not_found_is_not_retried():
    run, calls, sleep = fetch([httpx.Response(404)])

    with pytest.raises(FetchError, match="HTTP 404"):
        asyncio.run(run())
    assert len(calls) == 1
    assert sleep.pauses == []


def test_too_many_requests_respects_retry_after():
    run, _, sleep = fetch([httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, text="ok")])

    assert asyncio.run(run()) == "ok"
    assert sleep.pauses == [7.0]


def test_body_is_decoded_as_utf8_even_without_charset_header():
    body = "<p class=price_color>£51.77</p>".encode()
    run, _, _ = fetch([httpx.Response(200, content=body, headers={"Content-Type": "text/html"})])

    assert "£51.77" in asyncio.run(run())


def test_rate_limiter_spaces_request_starts_across_tasks():
    now = [100.0]
    pauses = []

    async def sleep(seconds):
        pauses.append(seconds)
        now[0] += seconds

    limiter = RateLimiter(0.5, clock=lambda: now[0], sleep=sleep)

    async def run():
        await asyncio.gather(*(limiter.wait() for _ in range(4)))

    asyncio.run(run())

    assert pauses == [0.5, 0.5, 0.5]
    assert now[0] == pytest.approx(101.5)
