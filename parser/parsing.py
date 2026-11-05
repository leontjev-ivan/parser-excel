"""HTML parsing for books.toscrape.com: catalogue pages and book pages.

Functions here are pure (HTML string in, model out) so they are tested
on saved pages without network access.
"""
from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .models import Book, ListItem, ListPage

RATING_WORDS = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}

_PRICE_RE = re.compile(r"\d+(?:[.,]\d+)?")
_PAGER_RE = re.compile(r"Page\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)
_AVAILABLE_RE = re.compile(r"\((\d+)\s+available\)", re.IGNORECASE)


class ParseError(ValueError):
    """The page does not look like the expected layout."""


def parse_rating(css_classes: Iterable[str]) -> int:
    """`<p class="star-rating Three">` -> 3."""
    for name in css_classes:
        if name in RATING_WORDS:
            return RATING_WORDS[name]
    raise ParseError(f"no rating word in classes {list(css_classes)!r}")


def parse_price(text: str) -> Decimal:
    """'£51.77' -> Decimal('51.77')."""
    match = _PRICE_RE.search(text)
    if not match:
        raise ParseError(f"no price in {text!r}")
    try:
        return Decimal(match.group().replace(",", "."))
    except InvalidOperation as exc:  # pragma: no cover - regex guarantees digits
        raise ParseError(f"bad price {text!r}") from exc


def parse_availability(text: str) -> tuple[bool, int | None]:
    """'In stock (22 available)' -> (True, 22); 'In stock' -> (True, None); 'Out of stock' -> (False, 0)."""
    clean = " ".join(text.split()).lower()
    if not clean:
        raise ParseError("empty availability")
    if "out of stock" in clean:
        return False, 0
    if "in stock" not in clean:
        raise ParseError(f"unknown availability {text!r}")
    match = _AVAILABLE_RE.search(clean)
    return True, int(match.group(1)) if match else None


def parse_pager(soup: BeautifulSoup) -> tuple[int, int]:
    """'Page 3 of 50' -> (3, 50). A catalogue without pager is a single page."""
    current = soup.select_one("ul.pager li.current")
    if current is None:
        return 1, 1
    match = _PAGER_RE.search(current.get_text())
    if not match:
        raise ParseError(f"unreadable pager {current.get_text(strip=True)!r}")
    return int(match.group(1)), int(match.group(2))


def parse_list_page(html: str, page_url: str) -> ListPage:
    """Catalogue page -> 20 books (title, price, rating, stock flag, links) + pagination."""
    soup = BeautifulSoup(html, "html.parser")
    pods = soup.select("article.product_pod")
    if not pods:
        raise ParseError(f"no books on catalogue page {page_url}")
    items = [_parse_pod(pod, page_url) for pod in pods]
    number, total = parse_pager(soup)
    next_link = soup.select_one("ul.pager li.next a[href]")
    next_url = urljoin(page_url, next_link["href"]) if next_link else None
    return ListPage(number=number, total=total, items=items, next_url=next_url)


def _parse_pod(pod: Tag, page_url: str) -> ListItem:
    link = _required(pod, "h3 a[href]", page_url)
    image = _required(pod, "div.image_container img[src]", page_url)
    rating = _required(pod, "p.star-rating", page_url)
    price = _required(pod, "p.price_color", page_url)
    availability = _required(pod, "p.availability", page_url)
    in_stock, _ = parse_availability(availability.get_text())
    return ListItem(
        # the visible text is cut ("A Light in the ..."), the title attribute is full
        title=(link.get("title") or link.get_text()).strip(),
        url=urljoin(page_url, link["href"]),
        price=parse_price(price.get_text()),
        rating=parse_rating(rating.get("class", [])),
        in_stock=in_stock,
        image_url=urljoin(page_url, image["src"]),
    )


def parse_book_page(html: str, page_url: str) -> Book:
    """Book page -> all fields: category from breadcrumbs, UPC and exact stock from the table."""
    soup = BeautifulSoup(html, "html.parser")
    main = _required(soup, "div.product_main", page_url)
    table = _product_table(soup)
    if "UPC" not in table or "Availability" not in table:
        raise ParseError(f"product table without UPC/Availability on {page_url}")
    in_stock, stock_count = parse_availability(table["Availability"])
    image = _required(soup, "#product_gallery img[src]", page_url)
    return Book(
        title=_required(main, "h1", page_url).get_text(strip=True),
        category=_category(soup),
        price=parse_price(_required(main, "p.price_color", page_url).get_text()),
        rating=parse_rating(_required(main, "p.star-rating", page_url).get("class", [])),
        in_stock=in_stock,
        stock_count=stock_count,
        url=page_url,
        image_url=urljoin(page_url, image["src"]),
        upc=table["UPC"],
    )


def _product_table(soup: BeautifulSoup) -> dict[str, str]:
    rows = {}
    for row in soup.select("table.table-striped tr"):
        th, td = row.find("th"), row.find("td")
        if th and td:
            rows[th.get_text(strip=True)] = td.get_text(" ", strip=True)
    return rows


def _category(soup: BeautifulSoup) -> str:
    # Home > Books > <Category> > <Title>: the category is the last link
    links = soup.select("ul.breadcrumb li a")
    return links[-1].get_text(strip=True) if len(links) >= 3 else ""


def _required(node: Tag, selector: str, page_url: str) -> Tag:
    found = node.select_one(selector)
    if found is None:
        raise ParseError(f"'{selector}' not found on {page_url}")
    return found
