from decimal import Decimal

import pytest

from parser.parsing import (
    ParseError,
    parse_availability,
    parse_book_page,
    parse_list_page,
    parse_price,
    parse_rating,
)

from .conftest import BASE, BOOK_URL, fixture, make_book


class TestListPage:
    def test_first_page_has_twenty_books_with_absolute_links(self):
        page = parse_list_page(fixture("page-1.html"), BASE + "page-1.html")

        assert len(page.items) == 20
        first = page.items[0]
        assert first.title == "A Light in the Attic"
        assert first.url == BOOK_URL
        assert first.price == Decimal("51.77")
        assert first.rating == 3
        assert first.in_stock is True
        assert first.image_url == "https://books.toscrape.com/media/cache/2c/da/2cdad67c44b002e7ead0cc35693c0e8b.jpg"
        assert all(item.url.startswith(BASE) and item.url.endswith("/index.html") for item in page.items)
        assert all(1 <= item.rating <= 5 for item in page.items)

    def test_full_title_is_taken_from_title_attribute_not_cut_text(self):
        html = fixture("page-1.html")
        assert "A Light in the ..." in html  # the visible text on the site is cut

        titles = [item.title for item in parse_list_page(html, BASE + "page-1.html").items]

        assert "Tipping the Velvet" in titles
        assert not any(title.endswith("...") for title in titles)

    def test_out_of_stock_books_are_flagged(self):
        html = fixture("page-1.html").replace("In stock", "Out of stock")

        page = parse_list_page(html, BASE + "page-1.html")

        assert not any(item.in_stock for item in page.items)

    def test_not_a_catalogue_page_raises(self):
        with pytest.raises(ParseError):
            parse_list_page("<html><body>Maintenance</body></html>", BASE + "page-1.html")


class TestPagination:
    @pytest.mark.parametrize(
        ("name", "number", "next_name"),
        [("page-1.html", 1, "page-2.html"), ("page-2.html", 2, "page-3.html"), ("page-50.html", 50, None)],
    )
    def test_current_page_total_and_next_link(self, name, number, next_name):
        page = parse_list_page(fixture(name), BASE + name)

        assert (page.number, page.total) == (number, 50)
        assert page.next_url == (BASE + next_name if next_name else None)

    def test_page_without_pager_is_single_page(self):
        html = fixture("page-1.html")
        start, end = html.index('<ul class="pager">'), html.index("</ul>", html.index('<ul class="pager">'))
        page = parse_list_page(html[:start] + html[end + 5:], BASE + "page-1.html")

        assert (page.number, page.total, page.next_url) == (1, 1, None)


class TestBookPage:
    def test_all_fields_from_book_page(self):
        book = parse_book_page(fixture("book-a-light-in-the-attic.html"), BOOK_URL)

        assert book == make_book()

    def test_out_of_stock_book_has_zero_count(self):
        html = fixture("book-a-light-in-the-attic.html").replace("In stock (22 available)", "Out of stock")

        book = parse_book_page(html, BOOK_URL)

        assert (book.in_stock, book.stock_count) == (False, 0)

    def test_catalogue_page_is_not_a_book_page(self):
        with pytest.raises(ParseError):
            parse_book_page(fixture("page-1.html"), BOOK_URL)


@pytest.mark.parametrize(
    ("word", "stars"), [("One", 1), ("Two", 2), ("Three", 3), ("Four", 4), ("Five", 5)]
)
def test_rating_word_to_number(word, stars):
    assert parse_rating(["star-rating", word]) == stars


def test_rating_without_word_raises():
    with pytest.raises(ParseError):
        parse_rating(["star-rating"])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("In stock (22 available)", (True, 22)),
        ("\n    In stock (1 available)\n", (True, 1)),
        ("In stock", (True, None)),
        ("Out of stock", (False, 0)),
    ],
)
def test_availability(text, expected):
    assert parse_availability(text) == expected


@pytest.mark.parametrize("text", ["", "Preorder"])
def test_unknown_availability_raises(text):
    with pytest.raises(ParseError):
        parse_availability(text)


@pytest.mark.parametrize(("text", "expected"), [("£51.77", "51.77"), ("Â£10.00", "10.00"), ("£7", "7")])
def test_price(text, expected):
    assert parse_price(text) == Decimal(expected)


def test_price_without_digits_raises():
    with pytest.raises(ParseError):
        parse_price("£")
