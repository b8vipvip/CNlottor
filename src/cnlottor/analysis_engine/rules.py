from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Sequence

from cnlottor.core import AnalysisResult, LotteryDraw, LotterySpec


def draw_tokens(spec: LotterySpec, draw: LotteryDraw) -> tuple[str, ...]:
    tokens = []
    for pool in spec.pools:
        numbers = draw.pools[pool.code]
        if pool.ordered:
            tokens.extend(f"{pool.code}:p{position + 1}={number}" for position, number in enumerate(numbers))
        else:
            tokens.extend(f"{pool.code}:n={number}" for number in numbers)
    return tuple(tokens)


class AssociationRuleAnalyzer:
    name = "association-rules"

    def __init__(self, min_support: float = 0.03, min_confidence: float = 0.2, limit: int = 1000):
        self.min_support = min_support
        self.min_confidence = min_confidence
        self.limit = limit

    def analyze(self, spec: LotterySpec, draws: Sequence[LotteryDraw]) -> AnalysisResult:
        selected = list(draws)[-self.limit:]
        transactions = [set(draw_tokens(spec, draw)) for draw in selected]
        singles = Counter(token for transaction in transactions for token in transaction)
        pairs = Counter(pair for transaction in transactions for pair in combinations(sorted(transaction), 2))
        total = max(len(transactions), 1)
        rules = []
        for pair, count in pairs.items():
            support = count / total
            if support < self.min_support:
                continue
            for antecedent, consequent in (pair, pair[::-1]):
                confidence = count / singles[antecedent]
                if confidence < self.min_confidence:
                    continue
                consequent_support = singles[consequent] / total
                rules.append({
                    "antecedent": antecedent,
                    "consequent": consequent,
                    "support": support,
                    "confidence": confidence,
                    "lift": confidence / consequent_support if consequent_support else 0.0,
                })
        rules.sort(key=lambda item: (item["lift"], item["confidence"], item["support"]), reverse=True)
        return AnalysisResult(spec.code, self.name, {"transactions": len(transactions), "rules": rules[:200]})
