from __future__ import annotations

from collections.abc import Mapping, Sequence

from cnlottor.core.lottery_spec import LotterySpec

from .base import LotteryProvider, RawDraw
from .cwl_official import ChinaWelfareLotteryProvider
from .datachart500 import DataChart500Provider, HttpSettings
from .text917500 import Text917500Provider


class FallbackLotteryProvider:
    """Try providers in order and preserve diagnostics from every failure."""

    def __init__(self, providers: Sequence[LotteryProvider]) -> None:
        if not providers:
            raise ValueError("at least one fallback provider is required")
        self.providers = tuple(providers)
        self.name = " -> ".join(provider.name for provider in self.providers)

    def fetch_draws(
        self,
        spec: LotterySpec,
        *,
        start_issue: str | None = None,
        end_issue: str | None = None,
    ) -> list[RawDraw]:
        failures = []
        for provider in self.providers:
            try:
                draws = list(
                    provider.fetch_draws(
                        spec,
                        start_issue=start_issue,
                        end_issue=end_issue,
                    )
                )
                if draws:
                    return draws
                failures.append(f"{provider.name}: no draws returned")
            except Exception as exc:
                failures.append(
                    f"{provider.name}: {type(exc).__name__}: {exc}"
                )
        raise RuntimeError(
            f"all providers failed for {spec.code}: " + " | ".join(failures)
        )

    def get_latest_issue(self, spec: LotterySpec) -> str | None:
        for provider in self.providers:
            try:
                issue = provider.get_latest_issue(spec)
                if issue:
                    return issue
            except Exception:
                continue
        return None


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


def build_default_provider(
    settings: HttpSettings = HttpSettings(),
) -> CompositeLotteryProvider:
    welfare = ChinaWelfareLotteryProvider(settings)
    datachart = DataChart500Provider(settings)
    text917500 = Text917500Provider(settings)
    return CompositeLotteryProvider(
        {
            # DataChart is reachable from common desktop and CI networks. The
            # official source remains a fallback when DataChart is unavailable.
            "ssq": FallbackLotteryProvider((datachart, welfare)),
            "sd": FallbackLotteryProvider((datachart, welfare)),
            "kl8": FallbackLotteryProvider((text917500, welfare)),
            "dlt": datachart,
            "pls": datachart,
            "qxc": datachart,
        }
    )
