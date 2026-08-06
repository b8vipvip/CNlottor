import importlib.metadata
import unittest

import cnlottor


class VersionTests(unittest.TestCase):
    def test_runtime_and_distribution_versions_match(self):
        self.assertEqual(cnlottor.__version__, "0.4.0")
        self.assertEqual(importlib.metadata.version("cnlottor"), cnlottor.__version__)


if __name__ == "__main__":
    unittest.main()
