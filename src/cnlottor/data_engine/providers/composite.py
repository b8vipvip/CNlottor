from __future__ import annotations

from collections.abc import Mapping

from cnlottor.core.lottery_spec import LotterySpec

from .base import LotteryProvider, RawDraw


class CompositeLotteryProvider:
    """Route each lottery to the provider that best supports its data shape."""

    name = "composite"

    def __init__(
        self,
        routes: Mapping[str, LotteryProvider],
        *,
        fallback: LotteryProvider | None = None,
    ) -> None:
        self.routes = {str(code).lower(): provider for code, provider in routes.items()}
        self.fallback = fallback

    def provider_for(self, spec: LotterySpec) -> LotteryProvider:
        provider = self.routes.get(spec.code)
        if provider is not None:
            return provider
        if self.fallback is not None:
            return self.fallback
        raise KeyError(f"no data provider configured for lottery {spec.code!r}")

    def fetch_draws(
        self,
        spec: LotterySpec,
        *,
        start_issue: str | None = None,
        end_issue: str | None = None,
    ) -> list[RawDraw]:
        provider = self.provider_for(spec)
        return list(
            provider.fetch_draws(
                spec,
                start_issue=start_issue,
                end_issue=end_issue,
            )
        )

    def get_latest_issue(self, spec: LotterySpec) -> str | None:
        return self.provider_for(spec).get_latest_issue(spec)
