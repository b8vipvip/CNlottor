from __future__ import annotations

from datetime import datetime, timezone

from cnlottor.core.registry import DEFAULT_REGISTRY, LotteryRegistry
from cnlottor.core.schemas import SyncReport
from cnlottor.core.storage import SQLiteDrawStore

from .normalizer import normalize_raw_draw
from .providers.base import LotteryProvider
from .validator import validate_draw_sequence


class DataSyncService:
    def __init__(
        self,
        store: SQLiteDrawStore,
        provider: LotteryProvider,
        registry: LotteryRegistry = DEFAULT_REGISTRY,
    ) -> None:
        self.store = store
        self.provider = provider
        self.registry = registry

    def sync(
        self,
        lottery_code: str,
        *,
        start_issue: str | None = None,
        end_issue: str | None = None,
    ) -> SyncReport:
        started_at = datetime.now(timezone.utc)
        spec = self.registry.get(lottery_code)
        raw_draws = self.provider.fetch_draws(
            spec,
            start_issue=start_issue,
            end_issue=end_issue,
        )
        normalized = [normalize_raw_draw(spec, raw) for raw in raw_draws]
        validated = validate_draw_sequence(spec, normalized)
        stored = self.store.upsert_draws(spec, validated)
        finished_at = datetime.now(timezone.utc)
        return SyncReport(
            lottery_code=spec.code,
            fetched=len(raw_draws),
            stored=stored,
            latest_issue=self.store.latest_issue(spec.code),
            started_at=started_at,
            finished_at=finished_at,
        )
