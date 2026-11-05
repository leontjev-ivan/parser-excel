import csv

from parser.export_csv import export_csv
from parser.table import HEADERS


def read_rows(path, delimiter):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.reader(stream, delimiter=delimiter))


def test_file_starts_with_utf8_bom(tmp_path, books):
    path = export_csv(books, tmp_path / "books.csv")

    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert "Цена, £".encode() in raw  # Cyrillic and the pound sign as UTF-8, not cp1251


def test_ru_format_semicolon_and_decimal_comma(tmp_path, books):
    rows = read_rows(export_csv(books, tmp_path / "books.csv", "ru"), ";")

    assert rows[0] == HEADERS
    assert rows[1] == [
        "A Light in the Attic", "Poetry", "51,77", "3", "да", "22", "a897fe39b1053632",
        "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
        "https://books.toscrape.com/media/cache/fe/72/fe72f0532301ec28892ae79a629a293c.jpg",
    ]
    assert len(rows) == 1 + len(books)


def test_std_format_comma_and_dot(tmp_path, books):
    rows = read_rows(export_csv(books, tmp_path / "books.csv", "std"), ",")

    assert rows[1][2] == "51.77"
    assert rows[0] == HEADERS


def test_special_characters_and_missing_values_round_trip(tmp_path, books):
    rows = read_rows(export_csv(books, tmp_path / "books.csv"), ";")

    lost = rows[4]
    assert lost[0] == 'Тест; "кавычки", £'
    assert (lost[1], lost[5], lost[6]) == ("", "", "")
