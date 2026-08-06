import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None

from cnlottor.api.app import create_app
from cnlottor.data_engine.providers import RawDraw


class FakeProvider:
    name = "fake"

    def fetch_draws(self, spec, *, start_issue=None, end_issue=None):
        pools = {}
        for pool in spec.pools:
            if pool.ordered:
                pools[pool.code] = tuple(pool.minimum for _ in range(pool.draw_count))
            else:
                pools[pool.code] = tuple(
                    range(pool.minimum, pool.minimum + pool.draw_count)
                )
        return [RawDraw(issue="2026001", pools=pools, source=self.name)]

    def get_latest_issue(self, spec):
        return "2026001"


@unittest.skipIf(TestClient is None, "FastAPI test dependencies are not installed")
class ApiTests(unittest.TestCase):
    def test_health_and_lotteries(self):
        with tempfile.TemporaryDirectory() as directory:
            client = TestClient(
                create_app(
                    Path(directory) / "test.db",
                    Path(directory) / "models",
                    provider=FakeProvider(),
                )
            )
            self.assertEqual(client.get("/health").status_code, 200)
            response = client.get("/lotteries")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                {item["code"] for item in response.json()},
                {"ssq", "dlt", "pls", "qxc", "sd", "kl8"},
            )

    def test_sync_and_status_for_desktop_client(self):
        with tempfile.TemporaryDirectory() as directory:
            client = TestClient(
                create_app(
                    Path(directory) / "test.db",
                    Path(directory) / "models",
                    provider=FakeProvider(),
                )
            )
            response = client.post("/sync/ssq")
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()["success"])
            status = client.get("/status/ssq")
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["draw_count"], 1)
            self.assertEqual(status.json()["latest_issue"], "2026001")
            self.assertFalse(status.json()["model_ready"])


if __name__ == "__main__":
    unittest.main()
