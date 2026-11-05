import functools
import io
from pathlib import Path

import pytest
from openpyxl import load_workbook

import parser.cli as cli
from parser.config import Settings
from parser.console import ConsoleReport, books_word, long_time, plural
from parser.crawler import CrawlResult, Progress, crawl_site

from .conftest import mock_site


def cli_args(tmp_path: Path, *extra: str) -> list[str]:
    return ["--out", str(tmp_path / "data"), "--log", str(tmp_path / "logs" / "parser.log"), *extra]


def test_run_against_mock_site_writes_excel_csv_and_log(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "crawl_site", functools.partial(crawl_site, transport=mock_site()))

    code = cli.main(cli_args(tmp_path, "--limit", "3"))

    out = capsys.readouterr().out
    assert code == cli.EXIT_OK
    assert load_workbook(tmp_path / "data" / "books.xlsx")["Книги"].max_row == 4  # header + 3 books
    assert (tmp_path / "data" / "books.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    assert "Страница  1 из 50" in out
    assert "Готово: 3 книги" in out
    assert str(tmp_path / "data" / "books.xlsx") in out
    log = (tmp_path / "logs" / "parser.log").read_text(encoding="utf-8")
    assert "GET https://books.toscrape.com/catalogue/page-1.html -> 200" in log


def test_stopped_crawl_still_saves_collected_books(tmp_path, monkeypatch, capsys, books):
    async def stopped(settings, result, on_page=None):
        result.books.extend(books[:2])
        result.error = "страница каталога page-2.html: HTTP 503"
        return result

    monkeypatch.setattr(cli, "crawl_site", stopped)

    code = cli.main(cli_args(tmp_path))

    out = capsys.readouterr().out
    assert code == cli.EXIT_PARTIAL
    assert "Остановлено: страница каталога page-2.html: HTTP 503" in out
    assert "Сохранено собранное: 2 книги" in out
    assert load_workbook(tmp_path / "data" / "books.xlsx")["Книги"].max_row == 3


def test_ctrl_c_saves_collected_books(tmp_path, monkeypatch, capsys, books):
    async def interrupted(settings, result, on_page=None):
        result.books.append(books[0])
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "crawl_site", interrupted)

    code = cli.main(cli_args(tmp_path))

    assert code == cli.EXIT_INTERRUPTED
    assert "Прервано вручную. Сохранено собранное: 1 книга" in capsys.readouterr().out
    assert (tmp_path / "data" / "books.csv").exists()


def test_unexpected_crash_saves_books_and_logs_traceback(tmp_path, monkeypatch, capsys, books):
    async def crashing(settings, result, on_page=None):
        result.books.extend(books[:3])
        raise RuntimeError("layout changed")

    monkeypatch.setattr(cli, "crawl_site", crashing)

    code = cli.main(cli_args(tmp_path))

    out = capsys.readouterr().out
    assert code == cli.EXIT_PARTIAL
    assert "Остановлено: непредвиденная ошибка RuntimeError: layout changed" in out
    assert load_workbook(tmp_path / "data" / "books.xlsx")["Книги"].max_row == 4
    assert "Traceback" in (tmp_path / "logs" / "parser.log").read_text(encoding="utf-8")


def test_locked_file_is_written_next_to_it(tmp_path):
    attempts = []

    def write(path):
        attempts.append(path)
        if len(attempts) == 1:
            raise PermissionError("open in Excel")
        return path

    saved = cli._save(write, tmp_path / "books.xlsx")

    assert saved.parent == tmp_path and saved.name.startswith("books-") and saved.suffix == ".xlsx"


def test_defaults_come_from_config():
    args = cli.build_arg_parser().parse_args([])
    defaults = Settings()

    assert (args.out, args.limit, args.delay, args.concurrency) == (defaults.out_dir, None, 0.5, 2)


@pytest.mark.parametrize(
    "args",
    [["--delay", "0.1"], ["--delay", "nan"], ["--delay", "inf"], ["--delay", "60"], ["--delay", "abc"],
     ["--concurrency", "4"], ["--concurrency", "0"], ["--limit", "0"], ["--limit", "abc"], ["--csv-format", "xls"]],
)
def test_unsafe_or_wrong_arguments_are_rejected(args, capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.build_arg_parser().parse_args(args)

    assert exit_info.value.code == 2
    assert "invalid _" not in capsys.readouterr().err  # no internal function names like "invalid _delay value"


def test_progress_line():
    now = [0.0]
    out = io.StringIO()
    report = ConsoleReport(out, clock=lambda: now[0])
    now[0] = 75.0

    report.page(Progress(page=10, pages_total=50, books=200, failed=1))

    assert out.getvalue() == "Страница 10 из 50 ████░░░░░░░░░░░░░░░░ собрано  200 · ошибок 1 · 01:15\n"


def test_final_report_lists_files(tmp_path):
    out = io.StringIO()
    report = ConsoleReport(out, clock=lambda: 545.0)
    result = CrawlResult(books=[], requests=1050)

    report.finish(result, [Path("data/books.xlsx"), Path("data/books.csv")], Path("logs/parser.log"))

    lines = out.getvalue().splitlines()
    assert lines[1].startswith("Готово: 0 книг за 0 с (1050 запросов)")
    assert lines[2:] == ["Excel: data/books.xlsx", "CSV:   data/books.csv", "Лог:   logs/parser.log"]


@pytest.mark.parametrize(
    ("count", "word"),
    [(1, "книга"), (2, "книги"), (4, "книги"), (5, "книг"), (11, "книг"), (12, "книг"),
     (21, "книга"), (22, "книги"), (111, "книг"), (1000, "книг")],
)
def test_russian_plural(count, word):
    assert books_word(count) == word


@pytest.mark.parametrize(("seconds", "text"), [(42, "42 с"), (545, "9 мин 05 с"), (1200, "20 мин 00 с")])
def test_long_time(seconds, text):
    assert long_time(seconds) == text


@pytest.mark.parametrize(("count", "word"), [(1, "запрос"), (21, "запрос"), (3, "запроса"), (21 + 1, "запроса"), (1050, "запросов")])
def test_requests_plural(count, word):
    assert plural(count, "запрос", "запроса", "запросов") == word
