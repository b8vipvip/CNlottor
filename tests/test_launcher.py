import subprocess
import sys
import unittest
from pathlib import Path


class LauncherTest(unittest.TestCase):
    def test_list_contains_all_modules(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, str(root / "cnlottor.py"), "list"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
        for name in ("tensorflow", "pytorch", "kl8"):
            self.assertIn(name, result.stdout)
            self.assertIn("available", result.stdout)


if __name__ == "__main__":
    unittest.main()
