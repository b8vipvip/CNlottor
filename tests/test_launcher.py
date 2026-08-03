import subprocess
import sys
import unittest
from pathlib import Path


class LauncherTest(unittest.TestCase):
    def test_list_contains_all_legacy_modules(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "cnlottor_cli.py"), "list"],
            cwd=root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        for name in ("tensorflow", "pytorch", "kl8"):
            self.assertIn(name, result.stdout)
            self.assertIn("available", result.stdout)

    def test_lotteries_contains_all_unified_games(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "cnlottor_cli.py"), "lotteries"],
            cwd=root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )
        for code in ("ssq", "dlt", "pls", "qxc", "sd", "kl8"):
            self.assertIn(code, result.stdout)


if __name__ == "__main__":
    unittest.main()
