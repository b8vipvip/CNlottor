import tempfile
import unittest
from pathlib import Path

from cnlottor.core import DEFAULT_REGISTRY, LotteryDraw

try:
    import torch
    from cnlottor.model_engine import TorchModelService, TrainConfig
except ImportError:
    torch = None


def draws_for(code: str, count: int = 24):
    spec = DEFAULT_REGISTRY.get(code)
    draws = []
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
        draws.append(LotteryDraw(code, f"{index + 1:04d}", pools, source="test"))
    return draws


@unittest.skipIf(torch is None, "PyTorch is not installed")
class TorchModelServiceTests(unittest.TestCase):
    def test_train_and_predict_ordered_and_set_lotteries(self):
        for code in ("pls", "ssq"):
            with self.subTest(lottery=code), tempfile.TemporaryDirectory() as directory:
                spec = DEFAULT_REGISTRY.get(code)
                draws = draws_for(code)
                service = TorchModelService(Path(directory))
                report = service.train(
                    spec,
                    draws,
                    TrainConfig(window_size=4, epochs=1, hidden_size=8),
                )
                self.assertTrue(Path(report.checkpoint).exists())
                prediction = service.predict(spec, draws)
                self.assertEqual(prediction.model_version, "0.4.0")
                for pool in spec.pools:
                    pool.validate_numbers(prediction.pools[pool.code])


if __name__ == "__main__":
    unittest.main()
