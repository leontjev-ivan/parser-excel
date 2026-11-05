"""Data model: what the parser extracts from the site."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ListItem:
    """A book as shown on a catalogue page: no category, UPC or exact stock."""

    title: str
    url: str
    price: Decimal
    rating: int
    in_stock: bool
    image_url: str


@dataclass(frozen=True)
class ListPage:
    """One catalogue page: its books and where to go next."""

    number: int
    total: int
    items: list[ListItem]
    next_url: str | None


@dataclass(frozen=True)
class Book:
    """A book with all fields from its own page."""

    title: str
    category: str
    price: Decimal
    rating: int  # 1-5 stars
    in_stock: bool
    stock_count: int | None  # None when the page did not say how many
    url: str
    image_url: str
    upc: str

    @classmethod
    def from_list_item(cls, item: ListItem) -> Book:
        """Fallback when the book page could not be loaded: keep what the catalogue showed."""
        return cls(
            title=item.title,
            category="",
            price=item.price,
            rating=item.rating,
            in_stock=item.in_stock,
            stock_count=None,
            url=item.url,
            image_url=item.image_url,
            upc="",
        )
