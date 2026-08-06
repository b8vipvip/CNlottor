from __future__ import annotations

import json
from dataclasses import asdict

from cnlottor.core import DEFAULT_REGISTRY
from cnlottor.data_engine import (
    ChinaWelfareLotteryProvider,
    CompositeLotteryProvider,
    DataChart500Provider,
    HttpSettings,
    normalize_raw_draw,
    validate_draw_sequence,
)


def main() -> int:
    settings = HttpSettings(timeout=30, retries=2, history_limit=5)
    welfare = ChinaWelfareLotteryProvider(
        settings,
        page_size=5,
        max_pages=1,
    )
    datachart = DataChart500Provider(settings)
    provider = CompositeLotteryProvider(
        {
            "ssq": welfare,
            "sd": welfare,
            "kl8": welfare,
            "dlt": datachart,
            "pls": datachart,
            "qxc": datachart,
        }
    )

    reports = []
    failures = []
    for spec in DEFAULT_REGISTRY.all():
        try:
            raw = provider.fetch_draws(spec)
            normalized = [normalize_raw_draw(spec, item) for item in raw]
            validated = validate_draw_sequence(spec, normalized)
            if not validated:
                raise ValueError("provider returned no validated draws")
            reports.append(
                {
                    "lottery_code": spec.code,
                    "provider": provider.provider_for(spec).name,
                    "draws": len(validated),
                    "latest_issue": max(draw.issue for draw in validated),
                    "sample": asdict(validated[0]),
                }
            )
        except Exception as exc:  # pragma: no cover - live diagnostics
            failures.append(
                {
                    "lottery_code": spec.code,
                    "provider": provider.provider_for(spec).name,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    print(
        json.dumps(
            {
                "success": not failures,
                "reports": reports,
                "failures": failures,
            },
            ensure_ascii=False,
            default=str,
            indent=2,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
