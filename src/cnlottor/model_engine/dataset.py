from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from cnlottor.core.lottery_spec import LotterySpec, NumberPoolSpec
from cnlottor.core.schemas import LotteryDraw


@dataclass(frozen=True, slots=True)
class EncodedPool:
    code: str
    encoding: str
    values: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class EncodedDraw:
    issue: str
    pools: Mapping[str, EncodedPool]


@dataclass(frozen=True, slots=True)
class SupervisedWindow:
    history: tuple[EncodedDraw, ...]
    target: EncodedDraw


def encode_pool(pool: NumberPoolSpec, numbers: Sequence[int]) -> EncodedPool:
    validated = pool.validate_numbers(numbers)
    if pool.ordered:
        values = tuple(number - pool.minimum for number in validated)
        return EncodedPool(pool.code, "ordered-class-index", values)

    vector = [0] * pool.pool_size
    for number in validated:
        vector[number - pool.minimum] = 1
    return EncodedPool(pool.code, "multi-hot", tuple(vector))


def encode_draw(spec: LotterySpec, draw: LotteryDraw) -> EncodedDraw:
    return EncodedDraw(
        issue=draw.issue,
        pools={
            pool.code: encode_pool(pool, draw.pools[pool.code])
            for pool in spec.pools
        },
    )


def build_supervised_windows(
    spec: LotterySpec,
    draws: Sequence[LotteryDraw],
    window_size: int,
) -> list[SupervisedWindow]:
    if window_size <= 0:
        raise ValueError("window_size must be positive")
    ordered_draws = sorted(draws, key=lambda draw: draw.issue)
    if len(ordered_draws) <= window_size:
        return []
    encoded = [encode_draw(spec, draw) for draw in ordered_draws]
    return [
        SupervisedWindow(
            history=tuple(encoded[index - window_size : index]),
            target=encoded[index],
        )
        for index in range(window_size, len(encoded))
    ]
