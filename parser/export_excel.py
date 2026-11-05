"""Excel export: sheet "Книги" with every book and sheet "Сводка" by category."""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .models import Book
from .summary import category_stats
from .table import HEADERS, book_row

BOOKS_SHEET = "Книги"
SUMMARY_SHEET = "Сводка"
SUMMARY_HEADERS = [
    "Категория",
    "Книг",
    "Средняя цена, £",
    "Мин. цена, £",
    "Макс. цена, £",
    "Средний рейтинг",
    "В наличии, шт.",
]

MONEY = "[$£-809]#,##0.00"  # pound sign, two decimals, thousands separator
INTEGER = "#,##0"
RATING = "0.00"

HEADER_FONT = Font(bold=True)
HEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
HEADER_BORDER = Border(bottom=Side(style="medium", color="5B9BD5"))
TOTAL_BORDER = Border(top=Side(style="thin", color="000000"))
CENTER = Alignment(horizontal="center")

# red (1 star) -> yellow (3) -> green (5), the classic Excel 3-color scale
RATING_SCALE = ColorScaleRule(
    start_type="num", start_value=1, start_color="F8696B",
    mid_type="num", mid_value=3, mid_color="FFEB84",
    end_type="num", end_value=5, end_color="63BE7B",
)

COL = {name: index for index, name in enumerate(HEADERS, start=1)}
PRICE_COL = COL["Цена, £"]
RATING_COL = COL["Рейтинг"]
LINK_COLS = (COL["Страница"], COL["Обложка"])
CENTERED_COLS = (RATING_COL, COL["В наличии"], COL["Кол-во, шт."])
MAX_WIDTH = {COL["Название"]: 60, COL["Страница"]: 48, COL["Обложка"]: 48}


def export_excel(books: Sequence[Book], path: Path) -> Path:
    workbook = Workbook()
    books_sheet = workbook.active
    assert isinstance(books_sheet, Worksheet)  # a new workbook always starts with one worksheet
    _fill_books(books_sheet, books)
    _fill_summary(workbook.create_sheet(SUMMARY_SHEET), books)
    workbook.save(path)
    return path


def _fill_books(ws: Worksheet, books: Sequence[Book]) -> None:
    ws.title = BOOKS_SHEET
    ws.append(HEADERS)
    for book in books:
        ws.append(book_row(book))
    last_row = ws.max_row
    _style_header(ws)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{last_row}"

    for row in ws.iter_rows(min_row=2, max_row=last_row):
        row[PRICE_COL - 1].number_format = MONEY
        for col in CENTERED_COLS:
            row[col - 1].alignment = CENTER
        for col in LINK_COLS:
            cell = row[col - 1]
            if cell.value:
                cell.hyperlink = str(cell.value)
                cell.style = "Hyperlink"
    if last_row >= 2:
        rating = get_column_letter(RATING_COL)
        ws.conditional_formatting.add(f"{rating}2:{rating}{last_row}", RATING_SCALE)
    _fit_columns(ws, MAX_WIDTH)


def _fill_summary(ws: Worksheet, books: Sequence[Book]) -> None:
    ws.append(SUMMARY_HEADERS)
    for row in category_stats(books):
        ws.append([row.category, row.books, row.avg_price, row.min_price, row.max_price, row.avg_rating, row.in_stock])
    last_row = ws.max_row
    _style_header(ws)
    ws.freeze_panes = "A2"
    # the filter covers categories only, so sorting never moves the total row
    ws.auto_filter.ref = f"A1:{get_column_letter(len(SUMMARY_HEADERS))}{last_row}"

    if books:
        ws.append(_total_row(last_row, len(books)))
        for cell in ws[ws.max_row]:
            cell.font = HEADER_FONT
            cell.border = TOTAL_BORDER

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        row[1].number_format = INTEGER
        for cell in row[2:5]:
            cell.number_format = MONEY
        row[5].number_format = RATING
        row[6].number_format = INTEGER
    _fit_columns(ws, {})


def _total_row(last_category_row: int, book_count: int) -> list[str]:
    """Counts add up from the category rows; averages and extremes come from the books
    sheet itself, because an average of category averages is not the overall average."""

    def books_range(col: int) -> str:
        letter = get_column_letter(col)
        return f"'{BOOKS_SHEET}'!{letter}2:{letter}{book_count + 1}"

    price, rating = books_range(PRICE_COL), books_range(RATING_COL)
    return [
        "Итого",
        f"=SUM(B2:B{last_category_row})",
        f"=AVERAGE({price})",
        f"=MIN({price})",
        f"=MAX({price})",
        f"=AVERAGE({rating})",
        f"=SUM(G2:G{last_category_row})",
    ]


def _style_header(ws: Worksheet) -> None:
    for cell in ws[1]:
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.border = HEADER_BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 30


def _fit_columns(ws: Worksheet, max_width: dict[int, int], default_max: int = 30) -> None:
    for index, column in enumerate(ws.iter_cols(), start=1):
        longest = max((_display_len(cell.value) for cell in column[1:]), default=0)
        header = len(str(column[0].value or "")) + 5  # bold text and the filter button
        limit = max_width.get(index, default_max)
        ws.column_dimensions[get_column_letter(index)].width = max(8, min(max(longest + 2, header), limit))


def _display_len(value: object) -> int:
    if value is None or (isinstance(value, str) and value.startswith("=")):
        return 0
    return len(str(value)) + (2 if not isinstance(value, str) else 0)  # numbers get a currency sign/separators
