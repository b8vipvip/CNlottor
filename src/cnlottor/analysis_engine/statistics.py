from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Sequence

from cnlottor.core.lottery_spec import LotterySpec, NumberPoolSpec
from cnlottor.core.schemas import AnalysisResult, LotteryDraw


def _frequency_for_pool(
    pool: NumberPoolSpec,
    draws: Sequence[LotteryDraw],
) -> dict[str, object]:
    if pool.ordered:
        position_counts = [Counter() for _ in range(pool.draw_count)]
        for draw in draws:
            for position, number in enumerate(draw.pools[pool.code]):
                position_counts[position][number] += 1
        return {
            "mode": "ordered",
            "positions": [dict(sorted(counter.items())) for counter in position_counts],
        }

    counts = Counter()
    for draw in draws:
        counts.update(draw.pools[pool.code])
    return {
        "mode": "set",
        "numbers": {
            number: counts.get(number, 0)
            for number in range(pool.minimum, pool.maximum + 1)
        },
    }


def frequency_analysis(spec: LotterySpec, draws: Sequence[LotteryDraw]) -> AnalysisResult:
    return AnalysisResult(
        lottery_code=spec.code,
        strategy="frequency",
        payload={
            "draw_count": len(draws),
            "pools": {
                pool.code: _frequency_for_pool(pool, draws)
                for pool in spec.pools
            },
        },
    )


def draw_shape_analysis(spec: LotterySpec, draws: Sequence[LotteryDraw]) -> AnalysisResult:
    pool_payload: dict[str, object] = {}
    for pool in spec.pools:
        sums: list[int] = []
        spans: list[int] = []
        odd = 0
        even = 0
        for draw in draws:
            values = draw.pools[pool.code]
            sums.append(sum(values))
            spans.append(max(values) - min(values))
            for value in values:
                if value % 2:
                    odd += 1
                else:
                    even += 1
        total = odd + even
        pool_payload[pool.code] = {
            "average_sum": (sum(sums) / len(sums) if sums else 0.0),
            "average_span": (sum(spans) / len(spans) if spans else 0.0),
            "odd_ratio": (odd / total if total else 0.0),
            "even_ratio": (even / total if total else 0.0),
        }
    return AnalysisResult(
        spec.code,
        "draw-shape",
        {"draw_count": len(draws), "pools": pool_payload},
    )


def co_occurrence_analysis(
    spec: LotterySpec,
    draws: Sequence[LotteryDraw],
    *,
    top_n: int = 20,
) -> AnalysisResult:
    pool_payload: dict[str, object] = {}
    for pool in spec.pools:
        counts: Counter[tuple[object, object]] = Counter()
        if pool.ordered:
            for draw in draws:
                tokens = [
                    (position, value)
                    for position, value in enumerate(draw.pools[pool.code])
                ]
                for left, right in combinations(tokens, 2):
                    counts[(left, right)] += 1
        else:
            for draw in draws:
                for pair in combinations(sorted(draw.pools[pool.code]), 2):
                    counts[pair] += 1
        pool_payload[pool.code] = [
            {"left": left, "right": right, "count": count}
            for (left, right), count in counts.most_common(top_n)
        ]
    return AnalysisResult(
        lottery_code=spec.code,
        strategy="co-occurrence",
        payload={"draw_count": len(draws), "pools": pool_payload},
    )
