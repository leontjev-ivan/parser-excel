import asyncio
import dataclasses

import httpx

from parser.config import Settings
from parser.crawler import CrawlResult, crawl, crawl_site
from parser.fetcher import Fetcher

from .conftest import BASE, BOOK_URL, fixture, mock_site

START = BASE + "page-1.html"


async def _no_sleep(_seconds: float) -> None:
    return None


def run_crawl(transport, *, limit=None, result=None, on_page=None):
    async def run():
        async with httpx.AsyncClient(transport=transport) as client:
            fetcher = Fetcher(client, delay=0, concurrency=2, retries=1, retry_pause=0, sleep=_no_sleep)
            return await crawl(fetcher, START, limit=limit, result=result, on_page=on_page)

    return asyncio.run(run())


def test_limit_stops_in_the_middle_of_second_page():
    progress = []

    result = run_crawl(mock_site(), limit=25, on_page=progress.append)

    assert len(result.books) == 25
    assert all(book.upc == "a897fe39b1053632" and book.category == "Poetry" for book in result.books)
    assert [(p.page, p.pages_total, p.books) for p in progress] == [(1, 50, 20), (2, 50, 25)]
    assert result.error is None and result.failed == []


def test_failed_book_page_keeps_catalogue_data():
    result = run_crawl(mock_site({BOOK_URL: 500}), limit=20)

    assert len(result.books) == 20
    assert result.failed == [BOOK_URL]
    lost = result.books[0]
    assert (lost.title, lost.category, lost.upc, lost.stock_count) == ("A Light in the Attic", "", "", None)
    assert str(lost.price) == "51.77"


def test_failed_catalogue_page_stops_and_keeps_collected_books():
    result = CrawlResult()

    run_crawl(mock_site({BASE + "page-2.html": 503}), result=result)

    assert len(result.books) == 20
    assert result.page == 1
    assert "page-2.html" in result.error


def test_interrupt_mid_page_keeps_books_already_downloaded():
    book_html = fixture("book-a-light-in-the-attic.html")
    served = 0
    hang = asyncio.Event()  # never set: book pages after the fifth never answer

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal served
        url = str(request.url)
        if url == START:
            return httpx.Response(200, content=fixture("page-1.html").encode("utf-8"))
        served += 1
        if served > 5:
            await hang.wait()
        return httpx.Response(200, content=book_html.encode("utf-8"))

    result = CrawlResult()

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            fetcher = Fetcher(client, delay=0, concurrency=2, retries=1, retry_pause=0, sleep=_no_sleep)
            task = asyncio.create_task(crawl(fetcher, START, result=result))
            while served < 7:  # five answered, two stuck in flight
                await asyncio.sleep(0.01)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    asyncio.run(run())

    assert len(result.books) == 5
    assert all(book.upc == "a897fe39b1053632" for book in result.books)


def test_crawl_ends_on_the_last_page():
    # shortcut the saved page 2 straight to the saved last page (50 of 50, no "next" link)
    page2 = fixture("page-2.html").replace('href="page-3.html"', 'href="page-50.html"')

    result = run_crawl(mock_site({BASE + "page-2.html": page2}))

    assert len(result.books) == 60
    assert (result.page, result.pages_total) == (50, 50)
    assert result.error is None


def test_real_client_sends_own_user_agent():
    seen: list[httpx.Request] = []
    settings = dataclasses.replace(Settings(), limit=1, delay=0, start_url=START)

    asyncio.run(crawl_site(settings, CrawlResult(), transport=mock_site(seen=seen)))

    assert len(seen) == 2  # one catalogue page + one book page
    assert {request.headers["User-Agent"] for request in seen} == {settings.user_agent}
    assert "python-httpx" not in settings.user_agent
