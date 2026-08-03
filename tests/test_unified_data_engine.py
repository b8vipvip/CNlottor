import tempfile
import unittest
from pathlib import Path

from cnlottor.core import DEFAULT_REGISTRY, SQLiteDrawStore
from cnlottor.data_engine import (
    DataSyncService,
    RawDraw,
    import_legacy_csv,
    normalize_raw_draw,
    validate_draw,
)


class FakeProvider:
    name = "fake"

    def fetch_draws(self, spec, *, start_issue=None, end_issue=None):
        if spec.code != "pls":
            raise AssertionError(f"unexpected lottery: {spec.code}")
        return [
            RawDraw(issue="2026001", pools={"digits": [3, 8, 3]}, source=self.name),
            RawDraw(issue="2026002", pools={"digits": [1, 0, 9]}, source=self.name),
        ]

    def get_latest_issue(self, spec):
        return "2026002"


class UnifiedDataEngineTests(unittest.TestCase):
    def test_unordered_pool_is_sorted_and_validated(self):
        spec = DEFAULT_REGISTRY.get("ssq")
        draw = normalize_raw_draw(
            spec,
            RawDraw(
                issue="2026001",
                pools={"main": [10, 1, 8, 6, 4, 2], "bonus": [9]},
            ),
        )
        self.assertEqual(draw.pools["main"], (1, 2, 4, 6, 8, 10))
        self.assertIs(validate_draw(spec, draw), draw)

    def test_ordered_digits_keep_positions_and_duplicates(self):
        spec = DEFAULT_REGISTRY.get("pls")
        draw = normalize_raw_draw(spec, RawDraw(issue="1", pools={"digits": [3, 8, 3]}))
        self.assertEqual(draw.pools["digits"], (3, 8, 3))
        validate_draw(spec, draw)

    def test_sync_service_stores_provider_results(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteDrawStore(Path(directory) / "cnlottor.db")
            report = DataSyncService(store, FakeProvider()).sync("pls")
            self.assertEqual(report.fetched, 2)
            self.assertEqual(report.stored, 2)
            self.assertEqual(report.latest_issue, "2026002")

    def test_import_existing_red_blue_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text(
                "期数,红球_1,红球_2,红球_3,红球_4,红球_5,红球_6,蓝球_1\n"
                "2026001,6,5,4,3,2,1,16\n",
                encoding="utf-8",
            )
            draws = import_legacy_csv(DEFAULT_REGISTRY.get("ssq"), path)
            self.assertEqual(draws[0].pools["main"], (1, 2, 3, 4, 5, 6))
            self.assertEqual(draws[0].pools["bonus"], (16,))


if __name__ == "__main__":
    unittest.main()
