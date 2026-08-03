import tempfile
import unittest
from pathlib import Path

from cnlottor.core import DEFAULT_REGISTRY, LotteryDraw, SQLiteDrawStore


class UnifiedCoreTests(unittest.TestCase):
    def test_registry_contains_all_supported_lotteries(self):
        self.assertEqual(
            DEFAULT_REGISTRY.codes(),
            ("dlt", "kl8", "pls", "qxc", "sd", "ssq"),
        )
        self.assertEqual(DEFAULT_REGISTRY.get("pl3").code, "pls")
        self.assertEqual(DEFAULT_REGISTRY.get("fc3d").code, "sd")

    def test_ordered_digit_pool_allows_duplicates(self):
        pool = DEFAULT_REGISTRY.get("pls").get_pool("digits")
        self.assertTrue(pool.ordered)
        self.assertFalse(pool.unique)
        self.assertEqual(pool.validate_numbers((3, 8, 3)), (3, 8, 3))

    def test_set_pool_rejects_duplicates(self):
        pool = DEFAULT_REGISTRY.get("ssq").get_pool("main")
        with self.assertRaises(ValueError):
            pool.validate_numbers((1, 1, 2, 3, 4, 5))

    def test_sqlite_round_trip_preserves_positions_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteDrawStore(Path(directory) / "cnlottor.db")
            spec = DEFAULT_REGISTRY.get("pls")
            store.upsert_draws(
                spec,
                [LotteryDraw("pls", "2026001", {"digits": (3, 8, 3)})],
            )
            draws = store.load_draws("pls")
            self.assertEqual(draws[0].pools["digits"], (3, 8, 3))

    def test_upsert_replaces_existing_issue(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteDrawStore(Path(directory) / "cnlottor.db")
            spec = DEFAULT_REGISTRY.get("pls")
            store.upsert_draws(spec, [LotteryDraw("pls", "1", {"digits": (1, 2, 3)})])
            store.upsert_draws(spec, [LotteryDraw("pls", "1", {"digits": (3, 2, 1)})])
            draws = store.load_draws("pls")
            self.assertEqual(len(draws), 1)
            self.assertEqual(draws[0].pools["digits"], (3, 2, 1))


if __name__ == "__main__":
    unittest.main()
