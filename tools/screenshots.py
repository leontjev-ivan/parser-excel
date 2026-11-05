"""Render README screenshots without opening any window.

* console: the captured output of a real run (data/console.txt) drawn as a dark terminal;
* sheets: data/books.xlsx read with openpyxl and drawn as an HTML grid using the file's
  own values, number formats, column widths, fills, borders, links and color scale.
  The total row has formulas without cached values (openpyxl does not calculate),
  so the simple SUM/AVERAGE/MIN/MAX formulas are evaluated here over the same file.

Usage (from the project folder, dev requirements installed):
    python tools/screenshots.py [--data data] [--shots shots]
"""
from __future__ import annotations

import argparse
import html
import re
from itertools import pairwise
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string, get_column_letter, range_boundaries
from openpyxl.utils.cell import coordinate_from_string
from openpyxl.worksheet.worksheet import Worksheet
from playwright.sync_api import sync_playwright

COMMAND = "python -m parser --out data/"
DURING_LINES = 17  # header + first pages: how the terminal looks mid-run
AFTER_LINES = 30  # a terminal of 30 rows scrolled to the end of the run

# ---------------------------------------------------------------- console

CONSOLE_CSS = """
body { margin: 0; background: #0b0d14; }
.term { width: 980px; background: #1a1b26; color: #c0caf5; font: 15px/1.5 'DejaVu Sans Mono', monospace;
        border: 1px solid #2a2e42; }
.bar { background: #24283b; color: #7a82a8; font-size: 13px; padding: 7px 14px; border-bottom: 1px solid #2a2e42; }
.bar i { display: inline-block; width: 11px; height: 11px; border-radius: 50%; margin-right: 6px; vertical-align: -1px; }
pre { margin: 0; padding: 14px 18px 18px; font: inherit; white-space: pre; }
.prompt { color: #9ece6a; } .cmd { color: #e0e6ff; } .dim { color: #565f89; } .bold { color: #e0e6ff; font-weight: bold; }
.full { color: #7dcfff; } .empty { color: #3b4261; } .ok { color: #9ece6a; font-weight: bold; } .warn { color: #e0af68; }
.label { color: #7aa2f7; } .cursor { background: #c0caf5; color: #1a1b26; }
"""


def console_html(lines: list[str], *, running: bool) -> str:
    body = [f'<span class="prompt">~/parser-excel $</span> <span class="cmd">{html.escape(COMMAND)}</span>']
    body += [_color_console_line(line) for line in lines]
    if running:
        body.append('<span class="cursor"> </span>')
    else:
        body.append('<span class="prompt">~/parser-excel $</span> <span class="cursor"> </span>')
    dots = "".join(f'<i style="background:{c}"></i>' for c in ("#f7768e", "#e0af68", "#9ece6a"))
    return (
        f"<!doctype html><meta charset=utf-8><style>{CONSOLE_CSS}</style>"
        f'<div class="term"><div class="bar">{dots} bash: parser-excel</div><pre>{chr(10).join(body)}</pre></div>'
    )


def _color_console_line(line: str) -> str:
    text = html.escape(line)
    if line.startswith("Парсер"):
        return f'<span class="bold">{text}</span>'
    if line.startswith("Задержка"):
        return f'<span class="dim">{text}</span>'
    if line.startswith("Страница"):
        text = re.sub(r"(█+)", r'<span class="full">\1</span>', text)
        text = re.sub(r"(░+)", r'<span class="empty">\1</span>', text)
        return re.sub(r"(· \d\d:\d\d)$", r'<span class="dim">\1</span>', text)
    if line.startswith("Готово"):
        return f'<span class="ok">{text}</span>'
    if line.startswith(("Остановлено", "Прервано", "Страницы книг")):
        return f'<span class="warn">{text}</span>'
    match = re.match(r"^(Excel:|CSV:|Лог:)(\s+)(.*)$", line)
    if match:
        label, space, path = (html.escape(part) for part in match.groups())
        return f'<span class="label">{label}</span>{space}{path}'
    return text


# ---------------------------------------------------------------- sheets

SHEET_CSS = """
body { margin: 0; background: #fff; font: 12.5px 'Liberation Sans', Arial, sans-serif; color: #000; }
.top { background: #217346; color: #fff; padding: 6px 12px; font-size: 13px; }
.fbar { display: flex; align-items: center; border-bottom: 1px solid #d4d4d4; height: 28px; font-size: 13px; }
.name { width: 86px; padding: 0 8px; border-right: 1px solid #d4d4d4; height: 100%; display: flex; align-items: center; }
.fx { width: 34px; text-align: center; color: #666; font-style: italic; border-right: 1px solid #d4d4d4; }
.formula { padding: 0 10px; } .formula code { font-family: 'DejaVu Sans Mono', monospace; font-size: 12.5px; }
table { border-collapse: collapse; table-layout: fixed; }
th { background: #f3f3f3; color: #444; font-weight: normal; border: 1px solid #d4d4d4; font-size: 12px; height: 20px; }
th.sel { background: #d3f0e0; color: #0e5c2f; border-bottom: 2px solid #217346; }
th.rsel { background: #d3f0e0; color: #0e5c2f; border-right: 2px solid #217346; }
td { border: 1px solid #e1e1e1; padding: 0 4px; height: 20px; white-space: nowrap; overflow: hidden;
     text-overflow: clip; position: relative; }
td.wrap { white-space: normal; line-height: 1.15; }
td.filter { padding-right: 18px; }
td.link { color: #0563c1; text-decoration: underline; }
td.cursor { outline: 2px solid #217346; outline-offset: -2px; }
tr.frozen td, tr.frozen th { border-bottom: 2px solid #9b9b9b; }
.flt { position: absolute; right: 2px; bottom: 2px; width: 13px; height: 13px; border: 1px solid #a5a5a5;
       background: #fff; font-size: 9px; line-height: 13px; text-align: center; color: #555; }
.tabs { display: flex; gap: 2px; border-top: 1px solid #d4d4d4; background: #f3f3f3; padding: 0 0 0 40px; font-size: 13px; }
.tab { padding: 5px 16px; color: #444; }
.tab.active { background: #fff; color: #217346; font-weight: bold; border-bottom: 3px solid #217346; }
"""

_FORMULA_RE = re.compile(r"^=(SUM|AVERAGE|MIN|MAX)\((?:'([^']+)'!)?([A-Z]+)(\d+):([A-Z]+)(\d+)\)$")


def evaluate(workbook, sheet: Worksheet, formula: str) -> float:
    """The few aggregate formulas the exporter writes; anything else is an error, not a guess."""
    match = _FORMULA_RE.match(formula)
    if not match:
        raise ValueError(f"unsupported formula {formula!r}")
    func, sheet_name, col1, row1, col2, row2 = match.groups()
    source = workbook[sheet_name] if sheet_name else sheet
    values = [
        cell.value
        for row in source.iter_rows(
            min_row=int(row1), max_row=int(row2),
            min_col=column_index_from_string(col1), max_col=column_index_from_string(col2),
        )
        for cell in row
        if isinstance(cell.value, (int, float))
    ]
    return {"SUM": sum, "MIN": min, "MAX": max, "AVERAGE": lambda v: sum(v) / len(v)}[func](values)


def format_value(value, number_format: str) -> str:
    """Display like Excel with Russian regional settings: '£51,77', '1 000', '2,93'."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if "£" in number_format:
        return "£" + _group(value, 2)
    if number_format == "0.00":
        return f"{value:.2f}".replace(".", ",")
    if number_format == "#,##0":
        return _group(value, 0)
    return f"{value:g}".replace(".", ",") if isinstance(value, float) else str(value)


def _group(value: float, decimals: int) -> str:
    return f"{value:,.{decimals}f}".replace(",", "\u00a0").replace(".", ",")


def color_scales(sheet: Worksheet) -> dict[str, list[tuple[float, tuple[int, int, int]]]]:
    """Column letter -> [(value, rgb), ...] stops of a numeric color scale."""
    scales = {}
    for fmt in sheet.conditional_formatting:
        for rule in fmt.rules:
            if rule.type != "colorScale":
                continue
            scale = rule.colorScale
            stops = [(float(c.val), _rgb(color.rgb)) for c, color in zip(scale.cfvo, scale.color, strict=True)]
            for cell_range in fmt.sqref.ranges:
                scales[get_column_letter(cell_range.min_col)] = stops
    return scales


def _rgb(argb: str) -> tuple[int, int, int]:
    code = argb[-6:]
    return int(code[0:2], 16), int(code[2:4], 16), int(code[4:6], 16)


def _scale_color(value: float, stops) -> str:
    """Linear interpolation between the neighbouring stops, like Excel does."""
    rgb = stops[0][1] if value <= stops[0][0] else stops[-1][1]
    for (v1, c1), (v2, c2) in pairwise(stops):
        if v1 <= value <= v2:
            t = (value - v1) / (v2 - v1)
            rgb = tuple(round(a + (b - a) * t) for a, b in zip(c1, c2, strict=True))
            break
    return "rgb({},{},{})".format(*rgb)


def sheet_html(workbook, name: str, *, max_rows: int, cursor: str, file_name: str) -> str:
    ws = workbook[name]
    last_col = ws.max_column
    last_row = min(ws.max_row, max_rows)
    cursor_col, cursor_row = coordinate_from_string(cursor)
    filter_cols = _filter_columns(ws)
    scales = color_scales(ws)

    cols = ['<col style="width:40px">']
    head = ['<tr><th></th>']
    table_width = 40
    for index in range(1, last_col + 1):
        letter = get_column_letter(index)
        # Excel column width is in characters of the default font: about 7 px each plus padding
        width = round((ws.column_dimensions[letter].width or 8.43) * 7 + 5)
        table_width += width
        cols.append(f'<col style="width:{width}px">')
        head.append(f'<th class="{"sel" if letter == cursor_col else ""}">{letter}</th>')
    head.append("</tr>")

    rows = []
    for row_index in range(1, last_row + 1):
        height = ws.row_dimensions[row_index].height
        style = f' style="height:{round(height * 96 / 72)}px"' if height else ""
        frozen = ' class="frozen"' if ws.freeze_panes and row_index == ws[ws.freeze_panes].row - 1 else ""
        cells = [f'<th class="{"rsel" if row_index == cursor_row else ""}">{row_index}</th>']
        for col_index in range(1, last_col + 1):
            cells.append(_cell_html(workbook, ws, ws.cell(row_index, col_index), filter_cols, scales, cursor))
        rows.append(f"<tr{frozen}{style}>{''.join(cells)}</tr>")

    cursor_value = ws[cursor].value
    formula = html.escape(str(cursor_value)) if cursor_value is not None else ""
    if formula.startswith("="):
        formula = f'<code>{formula}</code>'
    tabs = "".join(
        f'<span class="tab{" active" if sheet == name else ""}">{html.escape(sheet)}</span>'
        for sheet in workbook.sheetnames
    )
    return (
        f"<!doctype html><meta charset=utf-8><style>{SHEET_CSS}</style>"
        f'<div class="top">{html.escape(file_name)} · отрисовка файла, не окно Excel</div>'
        f'<div class="fbar"><div class="name">{cursor}</div><div class="fx">fx</div>'
        f'<div class="formula">{formula}</div></div>'
        f'<table style="width:{table_width}px">{"".join(cols)}{"".join(head)}{"".join(rows)}</table>'
        f'<div class="tabs">{tabs}</div>'
    )


def _filter_columns(ws: Worksheet) -> set[int]:
    if not ws.auto_filter.ref:
        return set()
    min_col, _, max_col, _ = range_boundaries(ws.auto_filter.ref)
    return set(range(min_col, max_col + 1))


def _cell_html(workbook, ws: Worksheet, cell, filter_cols, scales, cursor: str) -> str:
    value = cell.value
    if isinstance(value, str) and value.startswith("="):
        value = evaluate(workbook, ws, value)
    text = html.escape(format_value(value, cell.number_format))
    classes, styles = [], []
    if cell.coordinate == cursor:
        classes.append("cursor")
    if cell.hyperlink:
        classes.append("link")
    if cell.alignment.wrap_text:
        classes.append("wrap")
    button = ""
    if cell.row == 1 and cell.column in filter_cols:
        classes.append("filter")
        button = '<span class="flt">▼</span>'
    if cell.font.bold:
        styles.append("font-weight:bold")
    if cell.fill.fill_type == "solid":
        styles.append(f"background:#{cell.fill.fgColor.rgb[-6:]}")
    align = cell.alignment.horizontal or ("right" if isinstance(value, (int, float)) else "left")
    styles.append(f"text-align:{align}")
    if cell.alignment.vertical == "center":
        styles.append("vertical-align:middle")
    for side_name in ("top", "bottom"):
        side = getattr(cell.border, side_name)
        if side is not None and side.style:
            width = 2 if side.style == "medium" else 1
            color = side.color.rgb[-6:] if side.color is not None and isinstance(side.color.rgb, str) else "000000"
            styles.append(f"border-{side_name}:{width}px solid #{color}")
    if cell.column_letter in scales and isinstance(value, (int, float)) and cell.row > 1:
        styles.append(f"background:{_scale_color(float(value), scales[cell.column_letter])}")
    return f'<td class="{" ".join(classes)}" style="{";".join(styles)}">{text}{button}</td>'


# ---------------------------------------------------------------- main


def main() -> None:
    args = argparse.ArgumentParser(description="Render README screenshots headlessly")
    args.add_argument("--data", type=Path, default=Path("data"))
    args.add_argument("--shots", type=Path, default=Path("shots"))
    options = args.parse_args()
    options.shots.mkdir(exist_ok=True)

    console = (options.data / "console.txt").read_text(encoding="utf-8").splitlines()
    console = [line for line in console if not line.startswith("exit=")]
    workbook = load_workbook(options.data / "books.xlsx")
    summary_rows = workbook["Сводка"].max_row

    pages = {
        "01-console-progress.png": console_html(console[:DURING_LINES], running=True),
        "02-console-done.png": console_html(console[-AFTER_LINES:], running=False),
        "03-sheet-books.png": sheet_html(workbook, "Книги", max_rows=26, cursor="A1", file_name="books.xlsx"),
        "04-sheet-summary.png": sheet_html(
            workbook, "Сводка", max_rows=summary_rows, cursor=f"C{summary_rows}", file_name="books.xlsx"
        ),
    }
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1000, "height": 400})
            for name, content in pages.items():
                page.set_content(content)
                if "console" in name:
                    page.locator(".term").screenshot(path=str(options.shots / name))
                else:
                    # the sheet is as wide as its columns: fit the page to the table, shoot it whole
                    width = page.evaluate("Math.ceil(document.querySelector('table').getBoundingClientRect().width)")
                    page.set_viewport_size({"width": width, "height": 400})
                    page.screenshot(path=str(options.shots / name), full_page=True)
                    page.set_viewport_size({"width": 1000, "height": 400})
                print(options.shots / name)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
