"""Column order and headers shared by the Excel and CSV exports."""
from __future__ import annotations

from decimal import Decimal

from .models import Book

HEADERS = [
    "Название",
    "Категория",
    "Цена, £",
    "Рейтинг",
    "В наличии",
    "Кол-во, шт.",
    "UPC",
    "Страница",
    "Обложка",
]

Cell = str | int | Decimal | None


def book_row(book: Book) -> list[Cell]:
    """Raw values in HEADERS order; each exporter formats them its own way."""
    return [
        book.title,
        book.category,
        book.price,
        book.rating,
        "да" if book.in_stock else "нет",
        book.stock_count,
        book.upc,
        book.url,
        book.image_url,
    ]
