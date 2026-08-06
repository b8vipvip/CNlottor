import unittest

from cnlottor.analysis_engine import (
    AssociationRuleAnalyzer,
    CopulaConfig,
    GenericCopulaGenerator,
    RollingBacktester,
)
from cnlottor.core import DEFAULT_REGISTRY, LotteryDraw


LOTTERIES = ("ssq", "dlt", "pls", "qxc", "sd", "kl8")


def draws_for(code, count=80):
    spec = DEFAULT_REGISTRY.get(code)
    result = []
    for index in range(count):
        pools = {}
        for pool in spec.pools:
            if pool.ordered:
                pools[pool.code] = tuple(
                    (index + position) % pool.pool_size + pool.minimum
                    for position in range(pool.draw_count)
                )
            else:
                start = index % max(1, pool.pool_size - pool.draw_count + 1)
                pools[pool.code] = tuple(
                    range(
                        pool.minimum + start,
                        pool.minimum + start + pool.draw_count,
                    )
                )
        result.append(
            LotteryDraw(code, f"{index + 1:04d}", pools, source="test")
        )
    return result


class AdvancedAnalysisTests(unittest.TestCase):
    def test_rules_support_every_lottery(self):
        analyzer = AssociationRuleAnalyzer(
            min_support=0.01,
            min_confidence=0.01,
            min_occurrences=2,
        )
        for code in LOTTERIES:
            with self.subTest(lottery=code):
                result = analyzer.analyze(DEFAULT_REGISTRY.get(code), draws_for(code))
                self.assertEqual(result.strategy, "association-rules")
                self.assertTrue(result.payload["rules"])
                self.assertTrue(
                    all(rule["occurrences"] >= 2 for rule in result.payload["rules"])
                )

    def test_sparse_one_off_rules_are_filtered(self):
        spec = DEFAULT_REGISTRY.get("pls")
        draws = [
            LotteryDraw("pls", "0001", {"digits": (1, 2, 3)}, source="test"),
            LotteryDraw("pls", "0002", {"digits": (1, 2, 4)}, source="test"),
            LotteryDraw("pls", "0003", {"digits": (1, 5, 6)}, source="test"),
        ]
        result = AssociationRuleAnalyzer(
            min_support=0,
            min_confidence=0,
            min_occurrences=2,
            min_antecedent_occurrences=1,
        ).analyze(spec, draws)
        self.assertTrue(result.payload["rules"])
        self.assertTrue(
            all(rule["occurrences"] >= 2 for rule in result.payload["rules"])
        )

    def test_copula_generates_valid_candidates_for_every_lottery(self):
        generator = GenericCopulaGenerator(CopulaConfig(min_draws=10, samples=3))
        for code in LOTTERIES:
            with self.subTest(lottery=code):
                spec = DEFAULT_REGISTRY.get(code)
                candidates, diagnostics = generator.generate(spec, draws_for(code, 40))
                self.assertEqual(len(candidates), 3)
                self.assertGreater(diagnostics["dimensions"], 0)
                self.assertGreater(diagnostics["active_dimensions"], 0)
                self.assertEqual(
                    diagnostics["active_dimensions"]
                    + diagnostics["constant_dimensions"],
                    diagnostics["dimensions"],
                )
                for candidate in candidates:
                    for pool in spec.pools:
                        pool.validate_numbers(candidate[pool.code])

    def test_copula_handles_constant_features_without_runtime_warnings(self):
        spec = DEFAULT_REGISTRY.get("ssq")
        draws = []
        for index in range(40):
            main = (1, 2, 3, 4, 5, 6 + index % 3)
            draws.append(
                LotteryDraw(
                    "ssq",
                    f"{index + 1:04d}",
                    {"main": main, "bonus": (1 + index % 2,)},
                    source="test",
                )
            )
        candidates, diagnostics = GenericCopulaGenerator(
            CopulaConfig(min_draws=10, samples=2)
        ).generate(spec, draws)
        self.assertEqual(len(candidates), 2)
        self.assertGreater(diagnostics["constant_dimensions"], 0)

    def test_backtest_includes_random_baseline_for_every_lottery(self):
        for code in LOTTERIES:
            with self.subTest(lottery=code):
                result = RollingBacktester().run(
                    DEFAULT_REGISTRY.get(code),
                    draws_for(code),
                    window=20,
                )
                self.assertGreater(result.evaluated_draws, 0)
                self.assertIn("random_exact_rate", result.metrics)
                for pool in DEFAULT_REGISTRY.get(code).pools:
                    self.assertIn(f"mean_hits_{pool.code}", result.metrics)
                    self.assertIn(f"random_mean_hits_{pool.code}", result.metrics)


if __name__ == "__main__":
    unittest.main()
