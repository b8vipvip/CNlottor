from __future__ import annotations

from typing import Protocol, Sequence

from cnlottor.core.lottery_spec import LotterySpec
from cnlottor.core.schemas import LotteryDraw, PredictionResult


class ModelTrainer(Protocol):
    name: str

    def train(self, spec: LotterySpec, draws: Sequence[LotteryDraw]) -> str:
        """Train and return a model artifact identifier."""
        ...


class LotteryPredictor(Protocol):
    name: str

    def predict(
        self,
        spec: LotterySpec,
        draws: Sequence[LotteryDraw],
        *,
        model_artifact: str,
    ) -> PredictionResult:
        ...
