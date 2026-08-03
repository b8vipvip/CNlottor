import unittest

from cnlottor.analysis_engine import AnalysisService
from cnlottor.core import DEFAULT_REGISTRY, LotteryDraw
from cnlottor.model_engine import build_supervised_windows, encode_draw


class UnifiedModelAnalysisTests(unittest.TestCase):
    def test_set_pool_uses_multi_hot_encoding(self):
        spec = DEFAULT_REGISTRY.get("ssq")
        draw = LotteryDraw(
            "ssq",
            "1",
            {"main": (1, 2, 3, 4, 5, 6), "bonus": (16,)},
        )
        encoded = encode_draw(spec, draw)
        self.assertEqual(encoded.pools["main"].encoding, "multi-hot")
        self.assertEqual(sum(encoded.pools["main"].values), 6)
        self.assertEqual(len(encoded.pools["main"].values), 33)

    def test_ordered_pool_uses_position_class_indices(self):
        spec = DEFAULT_REGISTRY.get("pls")
        encoded = encode_draw(spec, LotteryDraw("pls", "1", {"digits": (0, 8, 3)}))
        self.assertEqual(encoded.pools["digits"].encoding, "ordered-class-index")
        self.assertEqual(encoded.pools["digits"].values, (0, 8, 3))

    def test_supervised_windows_are_chronological(self):
        spec = DEFAULT_REGISTRY.get("pls")
        draws = [
            LotteryDraw("pls", "3", {"digits": (3, 3, 3)}),
            LotteryDraw("pls", "1", {"digits": (1, 1, 1)}),
            LotteryDraw("pls", "2", {"digits": (2, 2, 2)}),
        ]
        windows = build_supervised_windows(spec, draws, 2)
        self.assertEqual([item.issue for item in windows[0].history], ["1", "2"])
        self.assertEqual(windows[0].target.issue, "3")

    def test_frequency_is_position_aware_for_digit_lotteries(self):
        spec = DEFAULT_REGISTRY.get("pls")
        draws = [
            LotteryDraw("pls", "1", {"digits": (3, 8, 3)}),
            LotteryDraw("pls", "2", {"digits": (3, 1, 9)}),
        ]
        result = AnalysisService().run("frequency", spec, draws)
        positions = result.payload["pools"]["digits"]["positions"]
        self.assertEqual(positions[0][3], 2)
        self.assertEqual(positions[1][8], 1)
        self.assertEqual(positions[2][3], 1)

    def test_set_frequency_and_shape_work_for_ssq(self):
        spec = DEFAULT_REGISTRY.get("ssq")
        draws = [
            LotteryDraw("ssq", "1", {"main": (1, 2, 3, 4, 5, 6), "bonus": (7,)}),
            LotteryDraw("ssq", "2", {"main": (1, 8, 9, 10, 11, 12), "bonus": (8,)}),
        ]
        service = AnalysisService()
        frequency = service.run("frequency", spec, draws)
        self.assertEqual(frequency.payload["pools"]["main"]["numbers"][1], 2)
        shape = service.run("draw-shape", spec, draws)
        self.assertGreater(shape.payload["pools"]["main"]["average_sum"], 0)


if __name__ == "__main__":
    unittest.main()
