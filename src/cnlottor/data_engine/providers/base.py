from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Mapping, Protocol, Sequence

from cnlottor.core.lottery_spec import LotterySpec


@dataclass(frozen=True, slots=True)
class RawDraw:
    issue: str
    pools: Mapping[str, Sequence[int | str]]
    draw_date: date | None = None
    source: str = "unknown"
    metadata: Mapping[str, Any] = field(default_factory=dict)


class LotteryProvider(Protocol):
    name: str

    def fetch_draws(
        self,
        spec: LotterySpec,
        *,
        start_issue: str | None = None,
        end_issue: str | None = None,
    ) -> Sequence[RawDraw]:
        ...

    def get_latest_issue(self, spec: LotterySpec) -> str | None:
        ...
