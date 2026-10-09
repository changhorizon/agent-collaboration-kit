"""Keep the OpenCode snapshot checker read-only and sensitive-content-free."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SANDBOX = ROOT / "sandbox"
SCRIPT = ROOT / "scripts" / "check_opencode_agents.py"
SNAPSHOT = ROOT / "integrations" / "opencode" / "agents"


class OpenCodeAgentChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SANDBOX)
        self.addCleanup(self.temp.cleanup)
        self.installed = Path(self.temp.name) / "agents"
        shutil.copytree(SNAPSHOT, self.installed)

    def run_check(self):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--installed-dir", str(self.installed)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_exact_snapshot_matches(self):
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.count("MATCH:"), 6)

    def test_drift_and_missing_file_fail_without_printing_contents(self):
        (self.installed / "lead.md").write_text("changed role\n", encoding="utf-8")
        (self.installed / "auditor.md").unlink()
        result = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("DRIFT: lead.md", result.stdout)
        self.assertIn("missing or linked installed file: auditor.md", result.stdout)
        self.assertNotIn("changed role", result.stdout)

    def test_symlink_is_rejected(self):
        (self.installed / "advisor.md").unlink()
        (self.installed / "advisor.md").symlink_to(SNAPSHOT / "advisor.md")
        result = self.run_check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing or linked installed file: advisor.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
