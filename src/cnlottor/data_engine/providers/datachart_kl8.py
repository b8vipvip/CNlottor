from __future__ import annotations

from urllib.parse import urlencode, urlparse

from cnlottor.core.lottery_spec import LotterySpec

from .base import RawDraw
from .datachart500 import HttpSettings


class DataChartKl8TrendProvider:
    """Parse recent KL8 draws from the live DataChart trend matrix.

    The old ``history/newinc/jbzs_redblue.php`` endpoint now returns 404.
    The main trend table remains available and marks drawn numbers with the
    CSS class ``chartBall01`` while omission cells use ``yl01``. Reading the
    class rather than the cell text avoids confusing omission counts with
    winning numbers.
    """

    name = "datachart.500.com/kl8-trend"
    allowed_domains = {"datachart.500.com"}
    base_url = "https://datachart.500.com/kl8/"

    def __init__(self, settings: HttpSettings = HttpSettings()) -> None:
        self.settings = settings

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

    def _get_text(
        self,
        *,
        start_issue: str | None = None,
        end_issue: str | None = None,
    ) -> str:
        params: dict[str, object] = {
            "expect": min(max(30, self.settings.history_limit), 100),
        }
        if start_issue:
            params["start"] = start_issue
        if end_issue:
            params["end"] = end_issue
        url = f"{self.base_url}?{urlencode(params)}"
        domain = urlparse(url).netloc.lower()
        if domain not in self.allowed_domains:
            raise ValueError(f"domain is not allowed: {domain}")
        response = self._session().get(
            url,
            timeout=self.settings.timeout,
            headers={
                "User-Agent": self.settings.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": "https://datachart.500.com/",
            },
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding or "utf-8"
        return response.text

    @staticmethod
    def parse_html(html: str) -> list[RawDraw]:
        try:
            from bs4 import BeautifulSoup
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "BeautifulSoup is required for KL8 trend parsing; install "
                "CNlottor with the 'data' extra"
            ) from exc

        soup = BeautifulSoup(html, "lxml")
        tbody = soup.find("tbody", id="tdata")
        if tbody is None:
            raise ValueError("KL8 trend table tbody#tdata was not found")

        draws: dict[str, RawDraw] = {}
        for row in tbody.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 81:
                continue
            issue = cells[0].get_text(strip=True)
            if not issue.isdigit():
                continue
            numbers = []
            for number, cell in enumerate(cells[1:81], start=1):
                classes = set(cell.get("class") or [])
                if "chartBall01" in classes:
                    numbers.append(number)
            if len(numbers) != 20:
                continue
            draws[issue] = RawDraw(
                issue=issue,
                pools={"main": numbers},
                source=DataChartKl8TrendProvider.name,
                metadata={"order": "ascending", "source_kind": "trend-matrix"},
            )

        if not draws:
            raise ValueError("no KL8 draws parsed from DataChart trend matrix")
        return list(draws.values())

    def fetch_draws(
        self,
        spec: LotterySpec,
        *,
        start_issue: str | None = None,
        end_issue: str | None = None,
    ) -> list[RawDraw]:
        if spec.code != "kl8":
            raise KeyError(f"KL8 trend provider only supports kl8, got {spec.code}")
        draws = self.parse_html(
            self._get_text(start_issue=start_issue, end_issue=end_issue)
        )
        return [
            draw
            for draw in draws
            if (start_issue is None or int(draw.issue) >= int(start_issue))
            and (end_issue is None or int(draw.issue) <= int(end_issue))
        ]

    def get_latest_issue(self, spec: LotterySpec) -> str | None:
        draws = self.fetch_draws(spec)
        return max((draw.issue for draw in draws), default=None, key=int)
