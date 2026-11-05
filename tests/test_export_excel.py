from decimal import Decimal

import pytest
from openpyxl import load_workbook

from parser.export_excel import BOOKS_SHEET, MONEY, SUMMARY_HEADERS, SUMMARY_SHEET, export_excel
from parser.table import HEADERS


@pytest.fixture
def workbook(tmp_path, books):
    path = export_excel(books, tmp_path / "books.xlsx")
    return load_workbook(path)


def test_two_sheets_in_order(workbook):
    assert workbook.sheetnames == [BOOKS_SHEET, SUMMARY_SHEET] == ["Книги", "Сводка"]


class TestBooksSheet:
    def test_header_is_bold_frozen_and_filtered(self, workbook):
        ws = workbook[BOOKS_SHEET]

        assert [cell.value for cell in ws[1]] == HEADERS
        assert all(cell.font.bold for cell in ws[1])
        assert ws.freeze_panes == "A2"
        assert ws.auto_filter.ref == "A1:I5"

    def test_values_types_and_money_format(self, workbook):
        ws = workbook[BOOKS_SHEET]

        assert [cell.value for cell in ws[2]][:7] == [
            "A Light in the Attic", "Poetry", 51.77, 3, "да", 22, "a897fe39b1053632",
        ]
        price = ws["C2"]
        assert isinstance(price.value, float)
        assert price.number_format == MONEY and "£" in price.number_format
        # the book whose page failed: no category, count or UPC, but still listed
        assert [ws["B5"].value, ws["F5"].value, ws["G5"].value] == [None, None, None]

    def test_links_are_clickable(self, workbook):
        ws = workbook[BOOKS_SHEET]

        for cell in (ws["H2"], ws["I2"]):
            assert cell.hyperlink is not None
            assert cell.hyperlink.target == cell.value
            assert cell.style == "Hyperlink"
        assert ws["H2"].value == "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"

    def test_rating_has_color_scale(self, workbook):
        ws = workbook[BOOKS_SHEET]

        rules = {str(fmt.sqref): [rule.type for rule in fmt.rules] for fmt in ws.conditional_formatting}
        assert rules == {"D2:D5": ["colorScale"]}

    def test_columns_are_sized_to_content(self, workbook):
        ws = workbook[BOOKS_SHEET]

        widths = {letter: ws.column_dimensions[letter].width for letter in "ABCDEFGHI"}
        assert all(8 <= width <= 60 for width in widths.values())
        assert widths["A"] > widths["D"]  # titles are wider than ratings


class TestSummarySheet:
    def test_one_row_per_category_largest_first(self, workbook):
        ws = workbook[SUMMARY_SHEET]

        assert [cell.value for cell in ws[1]] == SUMMARY_HEADERS
        rows = [[cell.value for cell in row] for row in ws.iter_rows(min_row=2, max_row=4)]
        assert rows == [
            ["Poetry", 2, 50.94, 50.1, 51.77, 2.0, 42],
            ["Mystery", 1, 47.82, 47.82, 47.82, 4.0, 20],
            ["Без категории", 1, 13.99, 13.99, 13.99, 5.0, 0],
        ]

    def test_total_row_uses_formulas_over_the_data(self, workbook):
        ws = workbook[SUMMARY_SHEET]

        assert [cell.value for cell in ws[5]] == [
            "Итого",
            "=SUM(B2:B4)",
            "=AVERAGE('Книги'!C2:C5)",
            "=MIN('Книги'!C2:C5)",
            "=MAX('Книги'!C2:C5)",
            "=AVERAGE('Книги'!D2:D5)",
            "=SUM(G2:G4)",
        ]
        assert all(cell.font.bold for cell in ws[5])
        assert ws.max_row == 5

    def test_formats_header_and_filter_without_total_row(self, workbook):
        ws = workbook[SUMMARY_SHEET]

        assert all(cell.font.bold for cell in ws[1])
        assert ws.freeze_panes == "A2"
        assert ws.auto_filter.ref == "A1:G4"  # sorting by filter never moves the total row
        assert [ws.cell(2, col).number_format for col in (3, 4, 5)] == [MONEY] * 3
        assert ws["F2"].number_format == "0.00"
        assert ws["C5"].number_format == MONEY


def test_empty_result_still_gives_valid_file(tmp_path):
    workbook = load_workbook(export_excel([], tmp_path / "empty.xlsx"))

    assert workbook[BOOKS_SHEET].max_row == 1
    assert workbook[BOOKS_SHEET].auto_filter.ref == "A1:I1"
    assert workbook[SUMMARY_SHEET].max_row == 1  # no total row over an empty range


def test_prices_stay_exact(tmp_path, books):
    workbook = load_workbook(export_excel(books, tmp_path / "books.xlsx"))

    prices = [Decimal(str(row[0].value)) for row in workbook[BOOKS_SHEET].iter_rows(min_row=2, min_col=3, max_col=3)]

    assert prices == [book.price for book in books]
