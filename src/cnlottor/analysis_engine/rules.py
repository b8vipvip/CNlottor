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
            tokens.extend(
                f"{pool.code}:p{position + 1}={number}"
                for position, number in enumerate(numbers)
            )
        else:
            tokens.extend(f"{pool.code}:n={number}" for number in numbers)
    return tuple(tokens)


class AssociationRuleAnalyzer:
    name = "association-rules"

    def __init__(
        self,
        min_support: float = 0.01,
        min_confidence: float = 0.2,
        min_occurrences: int = 3,
        min_antecedent_occurrences: int = 3,
        limit: int = 1000,
    ):
        if min_occurrences < 1 or min_antecedent_occurrences < 1:
            raise ValueError("rule occurrence thresholds must be positive")
        self.min_support = min_support
        self.min_confidence = min_confidence
        self.min_occurrences = min_occurrences
        self.min_antecedent_occurrences = min_antecedent_occurrences
        self.limit = limit

    def analyze(self, spec: LotterySpec, draws: Sequence[LotteryDraw]) -> AnalysisResult:
        selected = list(draws)[-self.limit :]
        transactions = [set(draw_tokens(spec, draw)) for draw in selected]
        singles = Counter(token for transaction in transactions for token in transaction)
        pairs = Counter(
            pair
            for transaction in transactions
            for pair in combinations(sorted(transaction), 2)
        )
        total = max(len(transactions), 1)
        rules = []
        discarded_sparse = 0
        for pair, count in pairs.items():
            if count < self.min_occurrences:
                discarded_sparse += 1
                continue
            support = count / total
            if support < self.min_support:
                continue
            for antecedent, consequent in (pair, pair[::-1]):
                antecedent_count = singles[antecedent]
                consequent_count = singles[consequent]
                if antecedent_count < self.min_antecedent_occurrences:
                    continue
                confidence = count / antecedent_count
                if confidence < self.min_confidence:
                    continue
                consequent_support = consequent_count / total
                rules.append(
                    {
                        "antecedent": antecedent,
                        "consequent": consequent,
                        "occurrences": count,
                        "antecedent_occurrences": antecedent_count,
                        "consequent_occurrences": consequent_count,
                        "support": support,
                        "confidence": confidence,
                        "lift": (
                            confidence / consequent_support
                            if consequent_support
                            else 0.0
                        ),
                    }
                )
        rules.sort(
            key=lambda item: (
                item["lift"],
                item["confidence"],
                item["occurrences"],
                item["support"],
            ),
            reverse=True,
        )
        return AnalysisResult(
            spec.code,
            self.name,
            {
                "transactions": len(transactions),
                "min_occurrences": self.min_occurrences,
                "discarded_sparse_pairs": discarded_sparse,
                "rules": rules[:200],
            },
        )
