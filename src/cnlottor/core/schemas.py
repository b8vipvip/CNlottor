from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class LotteryDraw:
    lottery_code: str
    issue: str
    pools: Mapping[str, tuple[int, ...]]
    draw_date: date | None = None
    source: str = "unknown"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        code = self.lottery_code.strip().lower()
        issue = str(self.issue).strip()
        if not code:
            raise ValueError("lottery_code must not be empty")
        if not issue:
            raise ValueError("issue must not be empty")
        normalized_pools = {
            str(pool_code): tuple(int(number) for number in numbers)
            for pool_code, numbers in self.pools.items()
        }
        object.__setattr__(self, "lottery_code", code)
        object.__setattr__(self, "issue", issue)
        object.__setattr__(self, "pools", normalized_pools)
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class SyncReport:
    lottery_code: str
    fetched: int
    stored: int
    latest_issue: str | None
    started_at: datetime
    finished_at: datetime


@dataclass(frozen=True, slots=True)
class PredictionResult:
    lottery_code: str
    issue: str | None
    pools: Mapping[str, tuple[int, ...]]
    model_name: str
    model_version: str | None = None
    scores: Mapping[str, tuple[float, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    lottery_code: str
    strategy: str
    payload: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class BacktestResult:
    lottery_code: str
    strategy: str
    evaluated_draws: int
    metrics: Mapping[str, float]
