from __future__ import annotations

from typing import Callable, Sequence

from cnlottor.core.lottery_spec import LotterySpec
from cnlottor.core.schemas import AnalysisResult, LotteryDraw

from .statistics import co_occurrence_analysis, draw_shape_analysis, frequency_analysis


AnalysisFunction = Callable[[LotterySpec, Sequence[LotteryDraw]], AnalysisResult]


class AnalysisService:
    def __init__(self) -> None:
        self._strategies: dict[str, AnalysisFunction] = {
            "frequency": frequency_analysis,
            "draw-shape": draw_shape_analysis,
            "co-occurrence": co_occurrence_analysis,
        }

    def register(self, name: str, strategy: AnalysisFunction, *, replace: bool = False) -> None:
        if name in self._strategies and not replace:
            raise ValueError(f"analysis strategy already registered: {name}")
        self._strategies[name] = strategy

    def run(
        self,
        strategy: str,
        spec: LotterySpec,
        draws: Sequence[LotteryDraw],
    ) -> AnalysisResult:
        try:
            function = self._strategies[strategy]
        except KeyError as exc:
            raise KeyError(f"unknown analysis strategy: {strategy}") from exc
        return function(spec, draws)

    def run_all(
        self,
        spec: LotterySpec,
        draws: Sequence[LotteryDraw],
    ) -> list[AnalysisResult]:
        return [function(spec, draws) for function in self._strategies.values()]
