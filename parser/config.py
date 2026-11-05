"""Default settings. Command-line flags override them (see cli.py)."""
from dataclasses import dataclass
from pathlib import Path

BASE_URL = "https://books.toscrape.com/"
START_URL = BASE_URL + "catalogue/page-1.html"

# Politeness limits: the crawler never starts requests more often than once
# per MIN_DELAY seconds and never keeps more than MAX_CONCURRENCY in flight.
MIN_DELAY = 0.5
MAX_DELAY = 10.0
MAX_CONCURRENCY = 3


@dataclass(frozen=True)
class Settings:
    start_url: str = START_URL
    out_dir: Path = Path("data")
    log_file: Path = Path("logs/parser.log")
    limit: int | None = None  # None = whole catalogue
    delay: float = 0.5  # minimal pause between request starts, seconds (global)
    concurrency: int = 2  # book pages loaded in parallel
    timeout: float = 20.0  # per request, seconds
    retries: int = 3  # extra attempts after a network error or HTTP 429/5xx
    retry_pause: float = 2.0  # first pause before a retry, doubles each time
    user_agent: str = "books-excel-parser/1.0 (educational scraping demo)"
    csv_format: str = "ru"  # "ru": ';' and decimal comma, "std": ',' and dot
