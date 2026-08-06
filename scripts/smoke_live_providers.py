from __future__ import annotations

import json
from dataclasses import asdict

from cnlottor.core import DEFAULT_REGISTRY
from cnlottor.data_engine import (
    HttpSettings,
    build_default_provider,
    normalize_raw_draw,
    validate_draw_sequence,
)


def _kl8_dom_diagnostics() -> dict:
    try:
        import requests
        from bs4 import BeautifulSoup

        response = requests.get(
            "https://datachart.500.com/kl8/",
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0 CNlottor/0.4",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        soup = BeautifulSoup(response.text, "lxml")
        tbody = soup.find("tbody", id="tdata")
        row = tbody.find("tr") if tbody else None
        cells = row.find_all("td") if row else []
        return {
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "row_classes": row.get("class") if row else None,
            "cells": [
                {
                    "index": index,
                    "text": cell.get_text(" ", strip=True),
                    "class": cell.get("class"),
                    "title": cell.get("title"),
                    "data": {
                        key: value
                        for key, value in cell.attrs.items()
                        if str(key).startswith("data-")
                    },
                }
                for index, cell in enumerate(cells[:90])
            ],
        }
    except Exception as exc:  # pragma: no cover - live diagnostics
        return {"diagnostic_error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    settings = HttpSettings(timeout=30, retries=2, history_limit=5)
    provider = build_default_provider(settings)

    reports = []
    failures = []
    for spec in DEFAULT_REGISTRY.all():
        routed = provider.provider_for(spec)
        try:
            raw = provider.fetch_draws(spec)
            normalized = [normalize_raw_draw(spec, item) for item in raw]
            validated = validate_draw_sequence(spec, normalized)
            if not validated:
                raise ValueError("provider returned no validated draws")
            reports.append(
                {
                    "lottery_code": spec.code,
                    "provider_route": routed.name,
                    "source_used": validated[0].source,
                    "draws": len(validated),
                    "latest_issue": max(draw.issue for draw in validated),
                    "sample": asdict(validated[0]),
                }
            )
        except Exception as exc:  # pragma: no cover - live diagnostics
            failure = {
                "lottery_code": spec.code,
                "provider_route": routed.name,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            if spec.code == "kl8":
                failure["datachart_dom"] = _kl8_dom_diagnostics()
            failures.append(failure)

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
