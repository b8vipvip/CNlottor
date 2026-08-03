from __future__ import annotations

import random
from collections import Counter
from typing import Sequence

from cnlottor.core import BacktestResult, LotteryDraw, LotterySpec


def score_prediction(spec: LotterySpec, predicted, actual: LotteryDraw):
    scores = {}
    for pool in spec.pools:
        expected = tuple(predicted[pool.code])
        observed = actual.pools[pool.code]
        scores[pool.code] = (
            sum(left == right for left, right in zip(expected, observed))
            if pool.ordered
            else len(set(expected) & set(observed))
        )
    return scores


def frequency_prediction(spec: LotterySpec, draws: Sequence[LotteryDraw]):
    result = {}
    for pool in spec.pools:
        if pool.ordered:
            values = []
            for position in range(pool.draw_count):
                counter = Counter(draw.pools[pool.code][position] for draw in draws)
                values.append(counter.most_common(1)[0][0])
            result[pool.code] = tuple(values)
        else:
            counter = Counter(number for draw in draws for number in draw.pools[pool.code])
            result[pool.code] = tuple(sorted(number for number, _ in counter.most_common(pool.draw_count)))
    return result


def random_prediction(spec: LotterySpec, rng: random.Random):
    result = {}
    for pool in spec.pools:
        universe = list(range(pool.minimum, pool.maximum + 1))
        if pool.ordered and not pool.unique:
            result[pool.code] = tuple(rng.choice(universe) for _ in range(pool.draw_count))
        else:
            result[pool.code] = tuple(sorted(rng.sample(universe, pool.draw_count)))
    return result


class RollingBacktester:
    def run(self, spec: LotterySpec, draws: Sequence[LotteryDraw], window: int = 60, seed: int = 42) -> BacktestResult:
        ordered = sorted(draws, key=lambda draw: draw.issue)
        if len(ordered) <= window:
            raise ValueError("not enough draws for rolling backtest")
        rng = random.Random(seed)
        totals = {pool.code: 0 for pool in spec.pools}
        random_totals = {pool.code: 0 for pool in spec.pools}
        exact = 0
        random_exact = 0
        evaluated = 0
        for index in range(window, len(ordered)):
            history = ordered[index - window:index]
            actual = ordered[index]
            prediction = frequency_prediction(spec, history)
            baseline = random_prediction(spec, rng)
            scores = score_prediction(spec, prediction, actual)
            random_scores = score_prediction(spec, baseline, actual)
            for code in totals:
                totals[code] += scores[code]
                random_totals[code] += random_scores[code]
            exact += int(all(scores[pool.code] == pool.draw_count for pool in spec.pools))
            random_exact += int(all(random_scores[pool.code] == pool.draw_count for pool in spec.pools))
            evaluated += 1
        metrics = {f"mean_hits_{code}": value / evaluated for code, value in totals.items()}
        metrics.update({f"random_mean_hits_{code}": value / evaluated for code, value in random_totals.items()})
        metrics["exact_rate"] = exact / evaluated
        metrics["random_exact_rate"] = random_exact / evaluated
        return BacktestResult(spec.code, "rolling-frequency-vs-random", evaluated, metrics)
