import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient
except ImportError:
    TestClient = None

from cnlottor.api.app import create_app


@unittest.skipIf(TestClient is None, "FastAPI test dependencies are not installed")
class ApiTests(unittest.TestCase):
    def test_health_and_lotteries(self):
        with tempfile.TemporaryDirectory() as directory:
            client = TestClient(create_app(Path(directory) / "test.db", Path(directory) / "models"))
            self.assertEqual(client.get("/health").status_code, 200)
            response = client.get("/lotteries")
            self.assertEqual(response.status_code, 200)
            self.assertEqual({item["code"] for item in response.json()}, {"ssq", "dlt", "pls", "qxc", "sd", "kl8"})


if __name__ == "__main__":
    unittest.main()
