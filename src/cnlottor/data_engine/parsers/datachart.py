from __future__ import annotations

import re
from datetime import date, datetime
from typing import Sequence

from cnlottor.core.lottery_spec import LotterySpec
from cnlottor.data_engine.providers.base import RawDraw

_DIGITS = re.compile(r"\d+")
_ISSUE = re.compile(r"^\d{5,8}$")
_DATE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$")
_INTEGER = re.compile(r"^\d+$")


def _text(node: object) -> str:
    return node.get_text(" ", strip=True)  # type: ignore[attr-defined]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.strip())


def _parse_date(texts: Sequence[str]) -> date | None:
    for text in texts:
        normalized = text.strip().replace("/", "-").replace(".", "-")
        if not _DATE.fullmatch(text.strip()):
            continue
        try:
            return datetime.strptime(normalized, "%Y-%m-%d").date()
        except ValueError:
            continue
    return None


def _issue_index(texts: Sequence[str]) -> int | None:
    for index, text in enumerate(texts):
        normalized = _normalize(text)
        if _DATE.fullmatch(text.strip()):
            continue
        if _ISSUE.fullmatch(normalized):
            return index
    return None


def _numeric_cells(texts: Sequence[str]) -> list[str]:
    values: list[str] = []
    for text in texts:
        compact = _normalize(text)
        if _INTEGER.fullmatch(compact):
            values.append(compact)
    return values


def _parse_compact_mixed_pools(
    cells: list[str],
    spec: LotterySpec,
) -> dict[str, list[int]] | None:
    """Parse a row where ordered digits and a special number share one cell.

    The current 7星彩 page may expose values such as ``45419914``: six basic
    digits followed by special number 14. Older rows can use seven characters,
    where the final character is the special number.
    """

    if len(spec.pools) != 2 or not cells:
        return None
    main, bonus = spec.pools
    value = cells[0]
    if not main.ordered or main.maximum > 9 or bonus.draw_count != 1:
        return None
    if len(value) <= main.draw_count:
        return None

    main_text = value[: main.draw_count]
    bonus_text = value[main.draw_count :]
    if not main_text.isdigit() or not bonus_text.isdigit():
        return None
    bonus_value = int(bonus_text)
    if not bonus.minimum <= bonus_value <= bonus.maximum:
        return None
    return {
        main.code: [int(char) for char in main_text],
        bonus.code: [bonus_value],
    }


def _parse_pools(texts: Sequence[str], spec: LotterySpec) -> dict[str, list[int]]:
    cells = _numeric_cells(texts)
    compact_mixed = _parse_compact_mixed_pools(cells, spec)
    if compact_mixed is not None:
        return compact_mixed

    cursor = 0
    pools: dict[str, list[int]] = {}
    for pool in spec.pools:
        if cursor >= len(cells):
            pools[pool.code] = []
            continue

        current = cells[cursor]
        if (
            pool.ordered
            and pool.maximum <= 9
            and len(current) == pool.draw_count
        ):
            pools[pool.code] = [int(char) for char in current]
            cursor += 1
            continue

        values = [int(value) for value in cells[cursor : cursor + pool.draw_count]]
        pools[pool.code] = values
        cursor += pool.draw_count

    return pools


def _rows(soup: object) -> Sequence[object]:
    tbody = soup.find("tbody", attrs={"id": "tdata"})  # type: ignore[attr-defined]
    if tbody is not None:
        return tbody.find_all("tr")
    table = soup.find("table", id="tablelist")  # type: ignore[attr-defined]
    if table is not None:
        return table.find_all("tr")
    return soup.find_all(  # type: ignore[attr-defined]
        "tr",
        class_=re.compile(r"(?:t_tr|chart)", re.I),
    )


def parse_datachart_html(spec: LotterySpec, html: str) -> list[RawDraw]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "BeautifulSoup is required for DataChart parsing; install CNlottor with the 'data' extra"
        ) from exc

    soup = BeautifulSoup(html, "lxml")
    parsed: list[RawDraw] = []
    for row in _rows(soup):
        cells = row.find_all("td")  # type: ignore[attr-defined]
        if not cells:
            continue
        texts = [_text(cell) for cell in cells]
        issue_index = _issue_index(texts)
        if issue_index is None:
            continue
        issue = _normalize(texts[issue_index])
        pools = _parse_pools(texts[issue_index + 1 :], spec)
        parsed.append(
            RawDraw(
                issue=issue,
                pools=pools,
                draw_date=_parse_date(texts),
                source="datachart.500.com",
            )
        )

    if not parsed:
        raise ValueError(f"no draw rows parsed for {spec.code}")
    return parsed
