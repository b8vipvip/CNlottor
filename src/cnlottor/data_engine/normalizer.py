from __future__ import annotations

from cnlottor.core.lottery_spec import LotterySpec
from cnlottor.core.schemas import LotteryDraw

from .providers.base import RawDraw


def normalize_raw_draw(spec: LotterySpec, raw: RawDraw) -> LotteryDraw:
    normalized: dict[str, tuple[int, ...]] = {}
    for pool in spec.pools:
        if pool.code not in raw.pools:
            raise ValueError(f"raw draw {raw.issue} is missing pool {pool.code!r}")
        values = tuple(int(value) for value in raw.pools[pool.code])
        if not pool.ordered:
            values = tuple(sorted(values))
        normalized[pool.code] = values

    unexpected = set(raw.pools) - {pool.code for pool in spec.pools}
    if unexpected:
        raise ValueError(f"raw draw {raw.issue} contains unexpected pools: {sorted(unexpected)}")

    return LotteryDraw(
        lottery_code=spec.code,
        issue=raw.issue,
        draw_date=raw.draw_date,
        pools=normalized,
        source=raw.source,
        metadata=raw.metadata,
    )
