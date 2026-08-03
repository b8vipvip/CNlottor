from __future__ import annotations

import re
from typing import Sequence

from cnlottor.core.lottery_spec import LotterySpec
from cnlottor.data_engine.providers.base import RawDraw


_DIGITS = re.compile(r"\d+")


def _text(node: object) -> str:
    return node.get_text(" ", strip=True)  # type: ignore[attr-defined]


def _digit_values(text: str, count: int) -> list[int]:
    tokens = _DIGITS.findall(text)
    if len(tokens) == 1 and len(tokens[0]) == count:
        return [int(char) for char in tokens[0]]
    return [int(token) for token in tokens[:count]]


def parse_datachart_html(spec: LotterySpec, html: str) -> list[RawDraw]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "BeautifulSoup is required for DataChart parsing; install CNlottor with the 'data' extra"
        ) from exc

    soup = BeautifulSoup(html, "lxml")
    if spec.code in {"ssq", "dlt", "kl8"}:
        tbody = soup.find("tbody", attrs={"id": "tdata"})
        if tbody is None:
            raise ValueError("missing draw table tbody#tdata")
        rows: Sequence[object] = tbody.find_all("tr")
    else:
        table = soup.find("table", id="tablelist")
        if table is None:
            raise ValueError("missing draw table table#tablelist")
        rows = table.find_all("tr")

    parsed: list[RawDraw] = []
    for row in rows:
        cells = row.find_all("td")  # type: ignore[attr-defined]
        if not cells:
            continue
        issue = _text(cells[0])
        if not issue or issue == "期号":
            continue

        if spec.code in {"pls", "sd", "qxc"}:
            pool = spec.pools[0]
            pools = {pool.code: _digit_values(_text(cells[1]), pool.draw_count)}
        elif spec.code == "kl8":
            pool = spec.pools[0]
            numbers: list[int] = []
            for cell in cells[1:]:
                numbers.extend(int(token) for token in _DIGITS.findall(_text(cell)))
            pools = {pool.code: numbers[: pool.draw_count]}
        else:
            cursor = 1
            pools: dict[str, list[int]] = {}
            for pool in spec.pools:
                values = [int(_text(cell)) for cell in cells[cursor : cursor + pool.draw_count]]
                pools[pool.code] = values
                cursor += pool.draw_count

        parsed.append(RawDraw(issue=issue, pools=pools, source="datachart.500.com"))

    if not parsed:
        raise ValueError(f"no draw rows parsed for {spec.code}")
    return parsed
