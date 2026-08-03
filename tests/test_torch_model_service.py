import tempfile
import unittest
from pathlib import Path

from cnlottor.core import DEFAULT_REGISTRY, LotteryDraw

try:
    from cnlottor.model_engine import TorchModelService, TrainConfig
    import torch
except ImportError:
    torch = None


@unittest.skipIf(torch is None, "PyTorch is not installed")
class TorchModelServiceTests(unittest.TestCase):
    def test_train_and_predict_ordered_lottery(self):
        spec = DEFAULT_REGISTRY.get("pls")
        draws = [
            LotteryDraw("pls", f"{index + 1:04d}", {"digits": (index % 10, (index + 1) % 10, (index + 2) % 10)}, source="test")
            for index in range(24)
        ]
        with tempfile.TemporaryDirectory() as directory:
            service = TorchModelService(Path(directory))
            report = service.train(spec, draws, TrainConfig(window_size=4, epochs=1, hidden_size=8))
            self.assertTrue(Path(report.checkpoint).exists())
            prediction = service.predict(spec, draws)
            spec.get_pool("digits").validate_numbers(prediction.pools["digits"])


if __name__ == "__main__":
    unittest.main()
