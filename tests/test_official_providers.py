import unittest

from cnlottor.core import DEFAULT_REGISTRY
from cnlottor.data_engine.providers import (
    ChinaWelfareLotteryProvider,
    CompositeLotteryProvider,
    RawDraw,
)


class StubCwlProvider(ChinaWelfareLotteryProvider):
    def __init__(self, payloads, page_size=2):
        super().__init__(page_size=page_size, max_pages=10)
        self.payloads = list(payloads)
        self.calls = []

    def _get_json(self, params):
        self.calls.append(dict(params))
        return self.payloads.pop(0) if self.payloads else {"result": []}


class StaticProvider:
    name = "static"

    def __init__(self, issue):
        self.issue = issue

    def fetch_draws(self, spec, *, start_issue=None, end_issue=None):
        pools = {
            pool.code: tuple(
                range(pool.minimum, pool.minimum + pool.draw_count)
                if not pool.ordered
                else (pool.minimum,) * pool.draw_count
            )
            for pool in spec.pools
        }
        return [RawDraw(issue=self.issue, pools=pools, source=self.name)]

    def get_latest_issue(self, spec):
        return self.issue


class OfficialProviderTests(unittest.TestCase):
    def test_cwl_parses_ssq_and_paginates(self):
        provider = StubCwlProvider(
            [
                {
                    "result": [
                        {"code": "2026002", "date": "2026-01-04(日)", "red": "01,02,03,04,05,06", "blue": "16"},
                        {"code": "2026001", "date": "2026-01-01", "red": "07,08,09,10,11,12", "blue": "01"},
                    ],
                    "pageCount": 2,
                },
                {
                    "result": [
                        {"code": "2025001", "date": "2025-01-01", "red": "13,14,15,16,17,18", "blue": "02"},
                    ],
                    "pageCount": 2,
                },
            ]
        )
        draws = provider.fetch_draws(DEFAULT_REGISTRY.get("ssq"))
        self.assertEqual(len(draws), 3)
        self.assertEqual(draws[0].pools["main"], [1, 2, 3, 4, 5, 6])
        self.assertEqual(draws[0].pools["bonus"], [16])
        self.assertEqual(draws[0].draw_date.isoformat(), "2026-01-04")
        self.assertEqual(len(provider.calls), 2)

    def test_cwl_parses_sd_and_kl8(self):
        sd = StubCwlProvider(
            [{"result": [{"code": "2026001", "date": "2026-01-01", "red": "3,8,3"}]}],
            page_size=30,
        ).fetch_draws(DEFAULT_REGISTRY.get("sd"))[0]
        self.assertEqual(sd.pools["digits"], [3, 8, 3])

        kl8_numbers = ",".join(f"{number:02d}" for number in range(1, 21))
        kl8 = StubCwlProvider(
            [{"result": [{"code": "2026001", "date": "2026-01-01", "red": kl8_numbers}]}],
            page_size=30,
        ).fetch_draws(DEFAULT_REGISTRY.get("kl8"))[0]
        self.assertEqual(kl8.pools["main"], list(range(1, 21)))

    def test_composite_routes_by_lottery_code(self):
        welfare = StaticProvider("2026001")
        sports = StaticProvider("26001")
        provider = CompositeLotteryProvider(
            {"ssq": welfare, "dlt": sports}
        )
        self.assertEqual(
            provider.fetch_draws(DEFAULT_REGISTRY.get("ssq"))[0].issue,
            "2026001",
        )
        self.assertEqual(
            provider.fetch_draws(DEFAULT_REGISTRY.get("dlt"))[0].issue,
            "26001",
        )


if __name__ == "__main__":
    unittest.main()
