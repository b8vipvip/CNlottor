from __future__ import annotations

import csv
from pathlib import Path

from cnlottor.core.lottery_spec import LotterySpec
from cnlottor.core.schemas import LotteryDraw

from ..validator import validate_draw


def _legacy_columns(spec: LotterySpec, pool_index: int) -> list[str]:
    pool = spec.pools[pool_index]
    prefix = "蓝球" if pool.code == "bonus" else "红球"
    return [f"{prefix}_{index + 1}" for index in range(pool.draw_count)]


def import_legacy_csv(spec: LotterySpec, path: str | Path) -> list[LotteryDraw]:
    results: list[LotteryDraw] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        for row in csv.DictReader(stream):
            issue = str(row.get("期数", "")).strip()
            if not issue:
                continue
            pools: dict[str, tuple[int, ...]] = {}
            for index, pool in enumerate(spec.pools):
                columns = _legacy_columns(spec, index)
                try:
                    values = tuple(int(row[column]) for column in columns)
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"legacy CSV row {issue} is missing valid columns for pool {pool.code}: {columns}"
                    ) from exc
                if not pool.ordered:
                    values = tuple(sorted(values))
                pools[pool.code] = values
            draw = LotteryDraw(
                lottery_code=spec.code,
                issue=issue,
                pools=pools,
                source=f"legacy-csv:{Path(path).name}",
            )
            results.append(validate_draw(spec, draw))
    return results
