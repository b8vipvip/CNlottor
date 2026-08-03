import unittest

from cnlottor.analysis_engine import AssociationRuleAnalyzer, CopulaConfig, GenericCopulaGenerator, RollingBacktester
from cnlottor.core import DEFAULT_REGISTRY, LotteryDraw


def draws_for(code, count=80):
    spec = DEFAULT_REGISTRY.get(code)
    result = []
    for index in range(count):
        pools = {}
        for pool in spec.pools:
            if pool.ordered:
                pools[pool.code] = tuple((index + position) % pool.pool_size + pool.minimum for position in range(pool.draw_count))
            else:
                start = index % max(1, pool.pool_size - pool.draw_count + 1)
                pools[pool.code] = tuple(range(pool.minimum + start, pool.minimum + start + pool.draw_count))
        result.append(LotteryDraw(code, f"{index + 1:04d}", pools, source="test"))
    return result


class AdvancedAnalysisTests(unittest.TestCase):
    def test_rules_support_ordered_and_set_lotteries(self):
        for code in ("ssq", "pls"):
            result = AssociationRuleAnalyzer(min_support=0.01, min_confidence=0.01).analyze(DEFAULT_REGISTRY.get(code), draws_for(code))
            self.assertEqual(result.strategy, "association-rules")
            self.assertTrue(result.payload["rules"])

    def test_copula_generates_valid_candidates(self):
        try:
            generator = GenericCopulaGenerator(CopulaConfig(min_draws=10, samples=3))
        except Exception as exc:
            self.skipTest(str(exc))
        for code in ("ssq", "pls"):
            spec = DEFAULT_REGISTRY.get(code)
            candidates, _ = generator.generate(spec, draws_for(code, 40))
            self.assertEqual(len(candidates), 3)
            for candidate in candidates:
                for pool in spec.pools:
                    pool.validate_numbers(candidate[pool.code])

    def test_backtest_includes_random_baseline(self):
        result = RollingBacktester().run(DEFAULT_REGISTRY.get("pls"), draws_for("pls"), window=20)
        self.assertGreater(result.evaluated_draws, 0)
        self.assertIn("random_exact_rate", result.metrics)


if __name__ == "__main__":
    unittest.main()
