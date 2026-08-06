from __future__ import annotations

import re
from datetime import date, datetime
from typing import Sequence

from cnlottor.core.lottery_spec import LotterySpec
from cnlottor.data_engine.providers.base import RawDraw

_DIGITS = re.compile(r"\d+")
_ISSUE = re.compile(r"^\d{5,8}$")
_DATE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}$")
_SMALL_INTEGER = re.compile(r"^\d{1,2}$")


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


def _ordered_digits(texts: Sequence[str], count: int) -> list[int]:
    collected: list[int] = []
    for text in texts:
        compact = _normalize(text)
        if not compact:
            continue
        # History tables sometimes put the complete result in one cell.
        if len(compact) == count and compact.isdigit():
            return [int(char) for char in compact]
        tokens = _DIGITS.findall(text)
        if len(tokens) >= count and all(len(token) == 1 for token in tokens[:count]):
            return [int(token) for token in tokens[:count]]
        # Current trend tables place each winning digit in a separate cell,
        # immediately after the issue column. Stop after the required count so
        # later omission/statistical cells are never mistaken for draw digits.
        if _SMALL_INTEGER.fullmatch(compact) and len(compact) == 1:
            collected.append(int(compact))
            if len(collected) == count:
                return collected
    return collected


def _set_numbers(texts: Sequence[str], spec: LotterySpec) -> dict[str, list[int]]:
    required = sum(pool.draw_count for pool in spec.pools)
    values: list[int] = []
    for text in texts:
        compact = _normalize(text)
        if not _SMALL_INTEGER.fullmatch(compact):
            continue
        values.append(int(compact))
        if len(values) == required:
            break

    pools: dict[str, list[int]] = {}
    cursor = 0
    for pool in spec.pools:
        pools[pool.code] = values[cursor : cursor + pool.draw_count]
        cursor += pool.draw_count
    return pools


def _rows(soup: object) -> Sequence[object]:
    tbody = soup.find("tbody", attrs={"id": "tdata"})  # type: ignore[attr-defined]
    if tbody is not None:
        return tbody.find_all("tr")
    table = soup.find("table", id="tablelist")  # type: ignore[attr-defined]
    if table is not None:
        return table.find_all("tr")
    return soup.find_all("tr", class_=re.compile(r"(?:t_tr|chart)", re.I))  # type: ignore[attr-defined]


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
        number_texts = texts[issue_index + 1 :]

        if spec.pools[0].ordered:
            pool = spec.pools[0]
            pools = {pool.code: _ordered_digits(number_texts, pool.draw_count)}
        else:
            pools = _set_numbers(number_texts, spec)

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
