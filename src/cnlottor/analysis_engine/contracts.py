from __future__ import annotations

from typing import Protocol, Sequence

from cnlottor.core.lottery_spec import LotterySpec
from cnlottor.core.schemas import AnalysisResult, LotteryDraw


class AnalysisStrategy(Protocol):
    name: str

    def supports(self, spec: LotterySpec) -> bool:
        ...

    def analyze(
        self,
        spec: LotterySpec,
        draws: Sequence[LotteryDraw],
    ) -> AnalysisResult:
        ...
