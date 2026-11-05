"""Crawl order: catalogue page -> its book pages -> next catalogue page.

Every field the task needs is on the book page (category in breadcrumbs,
UPC and exact stock in the table), so the catalogue is used only to find
books and as a fallback if a book page fails.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import httpx

from .config import Settings
from .fetcher import Fetcher, FetchError
from .models import Book, ListItem
from .parsing import ParseError, parse_book_page, parse_list_page

log = logging.getLogger(__name__)


@dataclass
class CrawlResult:
    """Filled in place, so whatever was collected survives an interrupt."""

    books: list[Book] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)  # book pages kept with catalogue data only
    page: int = 0
    pages_total: int = 0
    error: str | None = None  # why the crawl stopped before the end, if it did
    requests: int = 0


@dataclass(frozen=True)
class Progress:
    page: int
    pages_total: int
    books: int
    failed: int


OnPage = Callable[[Progress], None]


async def crawl(
    fetcher: Fetcher,
    start_url: str,
    *,
    limit: int | None = None,
    result: CrawlResult | None = None,
    on_page: OnPage | None = None,
) -> CrawlResult:
    result = result if result is not None else CrawlResult()
    url: str | None = start_url
    while url and (limit is None or len(result.books) < limit):
        try:
            page = parse_list_page(await fetcher.get_text(url), url)
        except (FetchError, ParseError) as exc:
            log.error("catalogue page failed, stopping: %s", exc)
            result.error = f"страница каталога {url}: {exc}"
            break
        items = page.items if limit is None else page.items[: limit - len(result.books)]
        tasks = [asyncio.ensure_future(_load_book(fetcher, item, result)) for item in items]
        try:
            books = await asyncio.gather(*tasks)
        except BaseException:
            # Interrupted mid-page: keep the books already downloaded, in catalogue order.
            result.books.extend(
                t.result() for t in tasks if t.done() and not t.cancelled() and t.exception() is None
            )
            raise
        result.books.extend(books)
        result.page, result.pages_total = page.number, page.total
        log.info("page %d/%d done, %d books total", page.number, page.total, len(result.books))
        if on_page:
            on_page(Progress(page.number, page.total, len(result.books), len(result.failed)))
        url = page.next_url
    return result


async def _load_book(fetcher: Fetcher, item: ListItem, result: CrawlResult) -> Book:
    try:
        return parse_book_page(await fetcher.get_text(item.url), item.url)
    except (FetchError, ParseError) as exc:
        log.warning("book page failed, keeping catalogue data: %s", exc)
        result.failed.append(item.url)
        return Book.from_list_item(item)


async def crawl_site(
    settings: Settings,
    result: CrawlResult,
    on_page: OnPage | None = None,
    transport: httpx.AsyncBaseTransport | None = None,  # tests pass a mock site here
) -> CrawlResult:
    """Real run: one HTTP client with our User-Agent for the whole crawl."""
    headers = {"User-Agent": settings.user_agent}
    async with httpx.AsyncClient(
        headers=headers, timeout=settings.timeout, follow_redirects=True, transport=transport
    ) as client:
        fetcher = Fetcher(
            client,
            delay=settings.delay,
            concurrency=settings.concurrency,
            retries=settings.retries,
            retry_pause=settings.retry_pause,
        )
        try:
            return await crawl(fetcher, settings.start_url, limit=settings.limit, result=result, on_page=on_page)
        finally:
            result.requests = fetcher.requests
