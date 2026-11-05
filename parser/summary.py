"""Per-category statistics for the summary sheet."""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .models import Book

UNKNOWN_CATEGORY = "Без категории"
CENT = Decimal("0.01")


@dataclass(frozen=True)
class CategoryStats:
    category: str
    books: int
    avg_price: Decimal
    min_price: Decimal
    max_price: Decimal
    avg_rating: float
    in_stock: int  # sum of known stock counts


def category_stats(books: Iterable[Book]) -> list[CategoryStats]:
    """One row per category, largest categories first, ties by name."""
    groups: dict[str, list[Book]] = defaultdict(list)
    for book in books:
        groups[book.category or UNKNOWN_CATEGORY].append(book)
    rows = [_stats(name, group) for name, group in groups.items()]
    return sorted(rows, key=lambda row: (-row.books, row.category))


def total_stats(books: Iterable[Book], label: str = "Итого") -> CategoryStats:
    return _stats(label, list(books))


def _stats(name: str, books: list[Book]) -> CategoryStats:
    if not books:
        return CategoryStats(name, 0, Decimal(0), Decimal(0), Decimal(0), 0.0, 0)
    prices = [book.price for book in books]
    return CategoryStats(
        category=name,
        books=len(books),
        avg_price=(sum(prices, Decimal(0)) / len(prices)).quantize(CENT, ROUND_HALF_UP),
        min_price=min(prices),
        max_price=max(prices),
        avg_rating=round(sum(book.rating for book in books) / len(books), 2),
        in_stock=sum(book.stock_count or 0 for book in books),
    )
