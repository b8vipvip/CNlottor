from __future__ import annotations

from urllib.parse import urlparse

from cnlottor.core.lottery_spec import LotterySpec

from .base import RawDraw
from .datachart500 import HttpSettings


class Text917500Provider:
    """Fetch KL8 draw-order history from the public 917500 text feed."""

    name = "data.917500.cn"
    allowed_domains = {"data.917500.cn"}
    url = "https://data.917500.cn/kl81000_cq_asc.txt"

    def __init__(self, settings: HttpSettings = HttpSettings()) -> None:
        self.settings = settings

    def _get_text(self) -> str:
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3 import Retry
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "requests is required for online synchronization; install "
                "CNlottor with the 'data' extra"
            ) from exc

        domain = urlparse(self.url).netloc.lower()
        if domain not in self.allowed_domains:
            raise ValueError(f"domain is not allowed: {domain}")
        session = requests.Session()
        retry = Retry(
            total=self.settings.retries,
            backoff_factor=self.settings.backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        session.mount("https://", HTTPAdapter(max_retries=retry))
        response = session.get(
            self.url,
            timeout=self.settings.timeout,
            headers={
                "User-Agent": self.settings.user_agent,
                "Accept": "text/plain,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    @staticmethod
    def parse_text(text: str) -> list[RawDraw]:
        draws: dict[str, RawDraw] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            first_segment = line.split(",", 1)[0]
            parts = [item for item in first_segment.split() if item]
            if len(parts) < 21:
                continue
            issue = parts[0]
            if not issue.isdigit():
                continue
            try:
                numbers = [int(value) for value in parts[1:21]]
            except ValueError:
                continue
            if len(numbers) != 20 or any(number < 1 or number > 80 for number in numbers):
                continue
            if len(set(numbers)) != 20:
                continue
            draws[issue] = RawDraw(
                issue=issue,
                pools={"main": numbers},
                source=Text917500Provider.name,
                metadata={"order": "draw-order"},
            )
        if not draws:
            raise ValueError("no KL8 rows parsed from 917500 text feed")
        return list(draws.values())

    def fetch_draws(
        self,
        spec: LotterySpec,
        *,
        start_issue: str | None = None,
        end_issue: str | None = None,
    ) -> list[RawDraw]:
        if spec.code != "kl8":
            raise KeyError(f"917500 provider only supports kl8, got {spec.code}")
        draws = self.parse_text(self._get_text())
        return [
            draw
            for draw in draws
            if (start_issue is None or int(draw.issue) >= int(start_issue))
            and (end_issue is None or int(draw.issue) <= int(end_issue))
        ]

    def get_latest_issue(self, spec: LotterySpec) -> str | None:
        draws = self.fetch_draws(spec)
        return max((draw.issue for draw in draws), default=None, key=int)
