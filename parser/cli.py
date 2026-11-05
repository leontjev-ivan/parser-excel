"""Command line: python -m parser --out data/ [--limit N] [--delay 1.0]."""
from __future__ import annotations

import argparse
import asyncio
import io
import logging
import math
import sys
from collections.abc import Callable, Sequence
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import MAX_CONCURRENCY, MAX_DELAY, MIN_DELAY, Settings
from .console import ConsoleReport
from .crawler import CrawlResult, crawl_site
from .export_csv import CSV_FORMATS, export_csv
from .export_excel import export_excel

log = logging.getLogger(__name__)

EXIT_OK, EXIT_PARTIAL, EXIT_INTERRUPTED = 0, 1, 130


def build_arg_parser() -> argparse.ArgumentParser:
    defaults = Settings()
    parser = argparse.ArgumentParser(
        prog="python -m parser",
        description="Собирает каталог books.toscrape.com и сохраняет его в Excel и CSV.",
    )
    parser.add_argument(
        "--out", type=Path, default=defaults.out_dir, help="папка для books.xlsx и books.csv (по умолчанию data/)"
    )
    parser.add_argument("--limit", type=_positive_int, default=None, help="собрать только первые N книг")
    parser.add_argument(
        "--delay", type=_delay, default=defaults.delay,
        help=f"пауза между запросами, с (не меньше {MIN_DELAY}, по умолчанию {defaults.delay})",
    )
    parser.add_argument(
        "--concurrency", type=_concurrency, default=defaults.concurrency,
        help=f"сколько страниц книг грузить одновременно, 1-{MAX_CONCURRENCY} (по умолчанию {defaults.concurrency})",
    )
    parser.add_argument(
        "--csv-format", choices=sorted(CSV_FORMATS), default=defaults.csv_format,
        help="ru: разделитель ';' и десятичная запятая (для русского Excel); std: ',' и точка",
    )
    parser.add_argument("--log", type=Path, default=defaults.log_file, help="файл лога (по умолчанию logs/parser.log)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    settings = Settings(
        out_dir=args.out,
        log_file=args.log,
        limit=args.limit,
        delay=args.delay,
        concurrency=args.concurrency,
        csv_format=args.csv_format,
    )
    _safe_console()
    setup_logging(settings.log_file)
    log.info("start: %s", settings)

    report = ConsoleReport()
    report.start(settings)
    result = CrawlResult()
    interrupted = False
    try:
        asyncio.run(crawl_site(settings, result, report.page))
    except KeyboardInterrupt:
        interrupted = True
        log.warning("interrupted by user after %d books", len(result.books))
    except Exception as exc:  # a bug or an unforeseen page: keep the data, the traceback goes to the log
        log.exception("crawl crashed after %d books", len(result.books))
        result.error = f"непредвиденная ошибка {type(exc).__name__}: {exc} (подробности в логе)"

    settings.out_dir.mkdir(parents=True, exist_ok=True)
    files = [
        _save(lambda path: export_excel(result.books, path), settings.out_dir / "books.xlsx"),
        _save(lambda path: export_csv(result.books, path, settings.csv_format), settings.out_dir / "books.csv"),
    ]
    log.info(
        "done: %d books, %d failed book pages, %d requests, error=%s, files=%s",
        len(result.books), len(result.failed), result.requests, result.error, [str(f) for f in files],
    )
    report.finish(result, files, settings.log_file, interrupted)
    if interrupted:
        return EXIT_INTERRUPTED
    return EXIT_PARTIAL if result.error else EXIT_OK


def setup_logging(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    # our fetcher logs every request itself; httpx would duplicate each line
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def _save(write: Callable[[Path], Path], path: Path) -> Path:
    """A file open in Excel is locked on Windows: write next to it instead of losing the data."""
    try:
        return write(path)
    except PermissionError:
        fallback = path.with_name(f"{path.stem}-{datetime.now():%Y%m%d-%H%M%S}{path.suffix}")
        log.warning("%s is locked (open in Excel?), writing %s", path, fallback)
        return write(fallback)


def _safe_console() -> None:
    # a console or pipe in a legacy code page must not crash on the progress bar characters
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(errors="replace")


def _number(text: str, kind: type, what: str):
    try:
        return kind(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"нужно {what}") from None


def _positive_int(text: str) -> int:
    value = _number(text, int, "целое число")
    if value < 1:
        raise argparse.ArgumentTypeError("нужно число больше 0")
    return value


def _delay(text: str) -> float:
    value = _number(text, float, "число секунд")
    if not math.isfinite(value) or value > MAX_DELAY:
        raise argparse.ArgumentTypeError(f"число секунд от {MIN_DELAY} до {MAX_DELAY}")
    if value < MIN_DELAY:
        raise argparse.ArgumentTypeError(f"не меньше {MIN_DELAY} с, чтобы не нагружать сайт")
    return value


def _concurrency(text: str) -> int:
    value = _number(text, int, "целое число")
    if not 1 <= value <= MAX_CONCURRENCY:
        raise argparse.ArgumentTypeError(f"от 1 до {MAX_CONCURRENCY}")
    return value

