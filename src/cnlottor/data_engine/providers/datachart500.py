from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from cnlottor.core.lottery_spec import LotterySpec

from ..parsers.datachart import parse_datachart_html
from .base import RawDraw


@dataclass(frozen=True, slots=True)
class HttpSettings:
    timeout: float = 20.0
    retries: int = 3
    backoff_factor: float = 0.6
    user_agent: str = "Mozilla/5.0 CNlottor/0.2"


class DataChart500Provider:
    name = "datachart.500.com"
    allowed_domains = {"datachart.500.com"}

    def __init__(self, settings: HttpSettings = HttpSettings()) -> None:
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
            headers={"User-Agent": self.settings.user_agent},
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text

    @staticmethod
    def _history_url(
        spec: LotterySpec,
        start_issue: str | None,
        end_issue: str | None,
    ) -> str:
        provider_code = spec.provider_code or spec.code
        base = f"https://datachart.500.com/{provider_code}/history/"
        if spec.code in {"qxc", "pls", "sd"}:
            path = "inc/history.php"
        elif spec.code == "kl8":
            path = "newinc/jbzs_redblue.php"
        else:
            return f"{base}history.shtml"

        start = int(start_issue) if start_issue else 1
        end = int(end_issue) if end_issue else 999999
        if end < start:
            raise ValueError("end_issue cannot be earlier than start_issue")
        return f"{base}{path}?start={start}&end={end}&limit={end - start + 1}"

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
            from bs4 import BeautifulSoup
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "BeautifulSoup is required for online synchronization; install CNlottor with the 'data' extra"
            ) from exc
        html = self._get_text(self._history_url(spec, None, None))
        soup = BeautifulSoup(html, "lxml")
        input_id = "to" if spec.code == "kl8" else "end"
        node = soup.find("input", id=input_id)
        return str(node.get("value")) if node and node.get("value") else None
