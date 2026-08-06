from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Mapping
from urllib.parse import urlparse

from cnlottor.core.lottery_spec import LotterySpec

from .base import RawDraw
from .datachart500 import HttpSettings

_NUMBER_RE = re.compile(r"\d+")
_DATE_RE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}")


class ChinaWelfareLotteryProvider:
    """Official JSON provider for SSQ, FC3D and KL8.

    The China Welfare Lottery endpoint returns records under ``result`` with
    common fields such as ``code``, ``date``, ``red`` and ``blue``. Requests
    are paged because the public endpoint normally returns at most 30 records.
    """

    name = "www.cwl.gov.cn"
    allowed_domains = {"www.cwl.gov.cn"}
    endpoint = (
        "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/"
        "findDrawNotice"
    )
    lottery_names = {
        "ssq": "ssq",
        "sd": "3d",
        "kl8": "kl8",
    }

    def __init__(
        self,
        settings: HttpSettings = HttpSettings(),
        *,
        page_size: int = 30,
        max_pages: int = 250,
    ) -> None:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        self.settings = settings
        self.page_size = page_size
        self.max_pages = max_pages

    def supports(self, spec: LotterySpec) -> bool:
        return spec.code in self.lottery_names

    def _session(self):
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3 import Retry
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "requests is required for online synchronization; install "
                "CNlottor with the 'data' extra"
            ) from exc

        session = requests.Session()
        retry = Retry(
            total=self.settings.retries,
            backoff_factor=self.settings.backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        return session

    def _get_json(self, params: Mapping[str, object]) -> Mapping[str, Any]:
        domain = urlparse(self.endpoint).netloc.lower()
        if domain not in self.allowed_domains:
            raise ValueError(f"domain is not allowed: {domain}")
        response = self._session().get(
            self.endpoint,
            params=params,
            timeout=self.settings.timeout,
            headers={
                "User-Agent": self.settings.user_agent,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": "https://www.cwl.gov.cn/ygkj/wqkjgg/",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise ValueError("unexpected CWL response payload")
        return payload

    @staticmethod
    def _numbers(value: object) -> list[int]:
        return [int(token) for token in _NUMBER_RE.findall(str(value or ""))]

    @staticmethod
    def _draw_date(value: object) -> date | None:
        match = _DATE_RE.search(str(value or ""))
        if match is None:
            return None
        return datetime.strptime(match.group(0), "%Y-%m-%d").date()

    def _parse_record(self, spec: LotterySpec, item: Mapping[str, Any]) -> RawDraw:
        issue = str(
            item.get("code")
            or item.get("issue")
            or item.get("lotteryDrawNum")
            or ""
        ).strip()
        if not issue:
            raise ValueError("CWL record is missing issue code")

        red = self._numbers(item.get("red") or item.get("number"))
        blue = self._numbers(item.get("blue"))
        if spec.code == "ssq":
            pools = {"main": red[:6], "bonus": blue[:1]}
        elif spec.code == "sd":
            pools = {"digits": red[:3]}
        elif spec.code == "kl8":
            pools = {"main": red[:20]}
        else:  # pragma: no cover - protected by supports()
            raise KeyError(f"unsupported CWL lottery: {spec.code}")

        return RawDraw(
            issue=issue,
            pools=pools,
            draw_date=self._draw_date(item.get("date")),
            source=self.name,
            metadata={"provider_name": item.get("name")},
        )

    def fetch_draws(
        self,
        spec: LotterySpec,
        *,
        start_issue: str | None = None,
        end_issue: str | None = None,
    ) -> list[RawDraw]:
        if not self.supports(spec):
            raise KeyError(f"unsupported CWL lottery: {spec.code}")

        records: dict[str, RawDraw] = {}
        for page_no in range(1, self.max_pages + 1):
            payload = self._get_json(
                {
                    "name": self.lottery_names[spec.code],
                    "issueCount": "",
                    "issueStart": start_issue or "",
                    "issueEnd": end_issue or "",
                    "dayStart": "",
                    "dayEnd": "",
                    "pageNo": page_no,
                    "pageSize": self.page_size,
                    "week": "",
                    "systemType": "PC",
                }
            )
            rows = payload.get("result") or []
            if not isinstance(rows, list):
                raise ValueError("CWL response field 'result' is not a list")
            if not rows:
                break

            for item in rows:
                if not isinstance(item, Mapping):
                    continue
                draw = self._parse_record(spec, item)
                records[draw.issue] = draw

            page_count = payload.get("pageCount") or payload.get("totalPage")
            if page_count is not None:
                try:
                    if page_no >= int(page_count):
                        break
                except (TypeError, ValueError):
                    pass
            if len(rows) < self.page_size:
                break

        if not records:
            raise ValueError(f"no official draw records returned for {spec.code}")
        return list(records.values())

    def get_latest_issue(self, spec: LotterySpec) -> str | None:
        if not self.supports(spec):
            return None
        payload = self._get_json(
            {
                "name": self.lottery_names[spec.code],
                "issueCount": "1",
                "pageNo": 1,
                "pageSize": 1,
                "systemType": "PC",
            }
        )
        rows = payload.get("result") or []
        if not isinstance(rows, list) or not rows:
            return None
        item = rows[0]
        return str(item.get("code") or "").strip() if isinstance(item, Mapping) else None
