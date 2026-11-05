"""Shared test helpers: saved pages of the site and a mock HTTP transport serving them."""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from parser.models import Book

FIXTURES = Path(__file__).parent / "fixtures"
BASE = "https://books.toscrape.com/catalogue/"
BOOK_URL = BASE + "a-light-in-the-attic_1000/index.html"

_PAGE_RE = re.compile(r"/catalogue/(page-\d+)\.html$")


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def mock_site(
    overrides: dict[str, int | str] | None = None, seen: list[httpx.Request] | None = None
) -> httpx.MockTransport:
    """Catalogue pages from fixtures, any book URL -> the saved book page.

    `overrides` maps a URL to a status code or an HTML body; `seen` collects requests.
    """
    overrides = overrides or {}
    book_html = fixture("book-a-light-in-the-attic.html")

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        url = str(request.url)
        body: int | str | None = overrides.get(url)
        if body is None:
            page = _PAGE_RE.search(url)
            if page:
                path = FIXTURES / f"{page.group(1)}.html"
                body = path.read_text(encoding="utf-8") if path.exists() else 404
            elif url.endswith("/index.html"):
                body = book_html
            else:
                body = 404
        if isinstance(body, int):
            return httpx.Response(body)
        # like the real site: UTF-8 bytes, no charset in Content-Type
        return httpx.Response(200, content=body.encode("utf-8"), headers={"Content-Type": "text/html"})

    return httpx.MockTransport(handler)


def make_book(**fields: object) -> Book:
    values: dict[str, object] = {
        "title": "A Light in the Attic",
        "category": "Poetry",
        "price": Decimal("51.77"),
        "rating": 3,
        "in_stock": True,
        "stock_count": 22,
        "url": BOOK_URL,
        "image_url": "https://books.toscrape.com/media/cache/fe/72/fe72f0532301ec28892ae79a629a293c.jpg",
        "upc": "a897fe39b1053632",
    }
    values.update(fields)
    return Book(**values)  # type: ignore[arg-type]


@pytest.fixture
def books() -> list[Book]:
    """Two categories, one book with a lost page (no category/UPC/stock), a title with CSV-hostile characters."""
    return [
        make_book(),
        make_book(title="Sharp Objects", category="Mystery", price=Decimal("47.82"), rating=4, stock_count=20,
                  url=BASE + "sharp-objects_997/index.html", upc="e00eb4fd7b871a48"),
        make_book(title="Soumission", price=Decimal("50.10"), rating=1, stock_count=20,
                  url=BASE + "soumission_998/index.html", upc="6957f44c3847a760"),
        make_book(title='Тест; "кавычки", £', category="", price=Decimal("13.99"), rating=5,
                  stock_count=None, url=BASE + "lost_1/index.html", upc=""),
    ]
