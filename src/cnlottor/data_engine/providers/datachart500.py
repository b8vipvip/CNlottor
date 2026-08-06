from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode, urlparse

from cnlottor.core.lottery_spec import LotterySpec

from ..parsers.datachart import parse_datachart_html
from .base import RawDraw


@dataclass(frozen=True, slots=True)
class HttpSettings:
    timeout: float = 20.0
    retries: int = 3
    backoff_factor: float = 0.6
    user_agent: str = "Mozilla/5.0 CNlottor/0.4"
    history_limit: int = 5000


class DataChart500Provider:
    name = "datachart.500.com"
    allowed_domains = {"datachart.500.com"}

    def __init__(self, settings: HttpSettings = HttpSettings()) -> None:
        if settings.history_limit < 1:
            raise ValueError("history_limit must be positive")
        self.settings = settings

    def _session(self):
        try:
            import requests
            from requests.adapters import HTTPAdapter
            from urllib3 import Retry
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "requests is required for online synchronization; install CNlottor with the 'data' extra"
            ) from exc
        session = requests.Session()
        retry = Retry(
            total=self.settings.retries,
            backoff_factor=self.settings.backoff_factor,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    def _get_text(self, url: str) -> str:
        domain = urlparse(url).netloc.lower()
        if domain not in self.allowed_domains:
            raise ValueError(f"domain is not allowed: {domain}")
        response = self._session().get(
            url,
            timeout=self.settings.timeout,
            headers={
                "User-Agent": self.settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Referer": "https://datachart.500.com/",
            },
        )
        response.raise_for_status()
        # Some DataChart endpoints declare GB2312 while others return UTF-8.
        # Number parsing is encoding agnostic, but choosing the detected encoding
        # preserves Chinese headers and makes diagnostics readable.
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        return response.text

    def _history_url(
        self,
        spec: LotterySpec,
        start_issue: str | None,
        end_issue: str | None,
        *,
        limit: int | None = None,
    ) -> str:
        provider_code = spec.provider_code or spec.code
        base = f"https://datachart.500.com/{provider_code}/history/"
        count = max(1, int(limit or self.settings.history_limit))

        if spec.code in {"ssq", "dlt"}:
            path = "newinc/history.php"
            params: dict[str, object] = {"limit": count, "sort": 1}
            if start_issue:
                params["start"] = start_issue
            if end_issue:
                params["end"] = end_issue
            return f"{base}{path}?{urlencode(params)}"

        if spec.code in {"qxc", "pls", "sd"}:
            path = "inc/history.php"
            params = {"expect": count}
            if start_issue:
                params["start"] = start_issue
            if end_issue:
                params["end"] = end_issue
            return f"{base}{path}?{urlencode(params)}"

        raise KeyError(
            f"DataChart history endpoint is not configured for {spec.code}; "
            "use the routed official provider"
        )

    @staticmethod
    def _issue_key(issue: str) -> tuple[int, str]:
        try:
            return int(issue), issue
        except ValueError:
            return -1, issue

    def fetch_draws(
        self,
        spec: LotterySpec,
        *,
        start_issue: str | None = None,
        end_issue: str | None = None,
    ) -> list[RawDraw]:
        url = self._history_url(spec, start_issue, end_issue)
        return parse_datachart_html(spec, self._get_text(url))

    def get_latest_issue(self, spec: LotterySpec) -> str | None:
        try:
            draws = self.fetch_draws(spec)
        except (KeyError, ValueError):
            return None
        if not draws:
            return None
        return max((draw.issue for draw in draws), key=self._issue_key)
