"""Console output: a progress line per catalogue page and the final report."""
from __future__ import annotations

import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TextIO

from .config import Settings
from .crawler import CrawlResult, Progress

BAR_WIDTH = 20


class ConsoleReport:
    def __init__(self, stream: TextIO | None = None, clock: Callable[[], float] = time.monotonic) -> None:
        self._out = stream or sys.stdout
        self._clock = clock
        self._started = clock()

    def start(self, settings: Settings) -> None:
        self._started = self._clock()
        scope = f"первые {settings.limit} книг" if settings.limit else "весь каталог"
        self._print("Парсер каталога books.toscrape.com")
        self._print(f"Задержка {format(settings.delay, 'g').replace('.', ',')} с · параллельно {settings.concurrency} · объём: {scope}")
        self._print()

    def page(self, progress: Progress) -> None:
        total = progress.pages_total or 1
        filled = round(BAR_WIDTH * progress.page / total)
        bar = "█" * filled + "░" * (BAR_WIDTH - filled)
        width = len(str(total))
        failed = f" · ошибок {progress.failed}" if progress.failed else ""
        self._print(
            f"Страница {progress.page:>{width}} из {total} {bar} "
            f"собрано {progress.books:>4}{failed} · {clock_time(self.elapsed)}"
        )

    def finish(self, result: CrawlResult, files: Sequence[Path], log_file: Path, interrupted: bool = False) -> None:
        self._print()
        count = len(result.books)
        if interrupted:
            self._print(f"Прервано вручную. Сохранено собранное: {count} {books_word(count)}")
        elif result.error:
            self._print(f"Остановлено: {result.error}")
            self._print(f"Сохранено собранное: {count} {books_word(count)}")
        else:
            self._print(
                f"Готово: {count} {books_word(count)} за {long_time(self.elapsed)} "
                f"({result.requests} {plural(result.requests, 'запрос', 'запроса', 'запросов')})"
            )
        if result.failed:
            self._print(f"Страницы книг не загрузились: {len(result.failed)}, у них данные из каталога (см. лог)")
        for path in files:
            label = "Excel" if path.suffix == ".xlsx" else path.suffix.lstrip(".").upper()
            self._print(f"{label + ':':<7}{path}")
        self._print(f"{'Лог:':<7}{log_file}")

    @property
    def elapsed(self) -> float:
        return self._clock() - self._started

    def _print(self, text: str = "") -> None:
        print(text, file=self._out, flush=True)


def clock_time(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"


def long_time(seconds: float) -> str:
    minutes, secs = divmod(round(seconds), 60)
    return f"{minutes} мин {secs:02d} с" if minutes else f"{secs} с"


def plural(count: int, one: str, few: str, many: str) -> str:
    """Russian plural form: 1 книга, 2 книги, 5 книг."""
    if count % 10 == 1 and count % 100 != 11:
        return one
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return few
    return many


def books_word(count: int) -> str:
    return plural(count, "книга", "книги", "книг")
