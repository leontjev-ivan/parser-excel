"""CSV export in UTF-8 with BOM: Excel then reads Cyrillic and the £ sign correctly."""
from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .models import Book
from .table import HEADERS, Cell, book_row


@dataclass(frozen=True)
class CsvFormat:
    delimiter: str
    decimal: str


CSV_FORMATS = {
    # Excel with Russian regional settings opens this by double click into columns
    "ru": CsvFormat(delimiter=";", decimal=","),
    # plain RFC 4180 style for scripts, Google Sheets, databases
    "std": CsvFormat(delimiter=",", decimal="."),
}


def export_csv(books: Sequence[Book], path: Path, fmt: str = "ru") -> Path:
    style = CSV_FORMATS[fmt]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter=style.delimiter)
        writer.writerow(HEADERS)
        for book in books:
            writer.writerow([_format(value, style) for value in book_row(book)])
    return path


def _format(value: Cell, style: CsvFormat) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}".replace(".", style.decimal)
    return str(value)
