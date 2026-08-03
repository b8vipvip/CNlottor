from __future__ import annotations

from collections import Counter

from cnlottor.core.lottery_spec import LotterySpec
from cnlottor.core.schemas import LotteryDraw


def validate_draw(spec: LotterySpec, draw: LotteryDraw) -> LotteryDraw:
    if draw.lottery_code != spec.code:
        raise ValueError(
            f"draw lottery code {draw.lottery_code!r} does not match {spec.code!r}"
        )
    expected = {pool.code for pool in spec.pools}
    actual = set(draw.pools)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(f"invalid pools; missing={missing}, unexpected={unexpected}")
    for pool in spec.pools:
        pool.validate_numbers(draw.pools[pool.code])
    return draw


def validate_draw_sequence(spec: LotterySpec, draws: list[LotteryDraw]) -> list[LotteryDraw]:
    validated = [validate_draw(spec, draw) for draw in draws]
    issue_counts = Counter(draw.issue for draw in validated)
    duplicates = sorted(issue for issue, count in issue_counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate issues returned by provider: {duplicates}")
    return validated
