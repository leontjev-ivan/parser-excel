from decimal import Decimal

from parser.summary import UNKNOWN_CATEGORY, category_stats, total_stats

from .conftest import make_book


def test_categories_sorted_by_size_then_name(books):
    names = [row.category for row in category_stats(books)]

    assert names == ["Poetry", "Mystery", UNKNOWN_CATEGORY]


def test_category_numbers(books):
    poetry = category_stats(books)[0]

    assert poetry.books == 2
    assert poetry.avg_price == Decimal("50.94")  # (51.77 + 50.10) / 2 = 50.935, rounded half up
    assert (poetry.min_price, poetry.max_price) == (Decimal("50.10"), Decimal("51.77"))
    assert poetry.avg_rating == 2.0
    assert poetry.in_stock == 42


def test_unknown_stock_counts_as_zero():
    stats = category_stats([make_book(stock_count=None), make_book(stock_count=3)])

    assert stats[0].in_stock == 3


def test_total_over_all_books(books):
    total = total_stats(books)

    assert (total.category, total.books, total.in_stock) == ("Итого", 4, 62)
    assert total.avg_price == Decimal("40.92")
    assert total.avg_rating == 3.25


def test_empty_input():
    assert category_stats([]) == []
    assert total_stats([]).books == 0
