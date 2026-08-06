import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WindowsBundleTests(unittest.TestCase):
    def test_launcher_supports_installed_python_versions_and_persistent_paths(self):
        script = (ROOT / "tools" / "windows" / "start_server.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn('Arguments = @("-3.12")', script)
        self.assertIn('Arguments = @("-3.11")', script)
        self.assertIn('Arguments = @("-3.10")', script)
        self.assertIn('$DataDirectory = Join-Path $Root "data"', script)
        self.assertIn('$Database = Join-Path $DataDirectory "cnlottor.db"', script)
        self.assertIn('$ModelsDirectory = Join-Path $Root "artifacts\\models"', script)
        self.assertIn("--database $Database", script)
        self.assertIn("--models $ModelsDirectory", script)
        self.assertIn('server\\cnlottor-*.whl', script)
        self.assertIn('$WheelWithExtras = "{0}[all]" -f $Wheel.FullName', script)

    def test_client_workflow_copies_tested_launcher_without_nested_zip(self):
        workflow = (
            ROOT / ".github" / "workflows" / "client-build.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("tools/windows/**", workflow)
        self.assertIn(
            "Copy-Item -Force tools\\windows\\start_server.ps1 "
            "package\\start_server.ps1",
            workflow,
        )
        self.assertIn("path: package", workflow)
        self.assertNotIn("Compress-Archive", workflow)

    def test_chinese_quick_start_is_shipped(self):
        instructions = (
            ROOT / "tools" / "windows" / "使用说明.txt"
        ).read_text(encoding="utf-8")
        self.assertIn("Python 3.12", instructions)
        self.assertIn("同步数据", instructions)
        self.assertIn("训练模型", instructions)
        self.assertIn("data\\cnlottor.db", instructions)


if __name__ == "__main__":
    unittest.main()
