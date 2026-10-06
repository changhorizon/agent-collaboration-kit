"""Ensure installation stays project-local and never overwrites existing protocols."""

import sys
import tempfile
import unittest
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX.parent / "scripts"))
from install import FILES, RELATIVE_DEST, install  # noqa: E402


class InstallChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SANDBOX)
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "consumer"
        self.target.mkdir()

    def test_dry_run_does_not_create_files(self):
        plan = install(self.target, dry_run=True)
        self.assertEqual(len(plan), len(FILES) + 1)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_install_preserves_existing_agents_and_is_self_contained(self):
        agents = self.target / "AGENTS.md"
        existing = "# Consumer instructions\n\nKeep this paragraph unchanged.\n"
        agents.write_text(existing, encoding="utf-8")
        install(self.target)
        self.assertTrue(agents.read_text(encoding="utf-8").startswith(existing))
        self.assertIn(str(RELATIVE_DEST / "collaboration.md"), agents.read_text(encoding="utf-8"))
        destination = self.target / RELATIVE_DEST
        self.assertEqual(
            sorted(p.relative_to(destination).as_posix() for p in destination.rglob("*.md")),
            sorted(FILES),
        )
        for path in destination.rglob("*.md"):
            self.assertNotIn(str(SANDBOX.parent.resolve()), path.read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "existing installation"):
            install(self.target)

    def test_existing_complete_local_protocol_is_not_replaced(self):
        old = self.target / ".agent"
        (old / "exchange").mkdir(parents=True)
        (old / "collaboration.md").write_text("existing protocol\n", encoding="utf-8")
        (old / "exchange/README.md").write_text("existing messages\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "complete local protocol"):
            install(self.target)
        self.assertFalse((self.target / RELATIVE_DEST).exists())

    def test_existing_local_agents_pointer_is_not_duplicated(self):
        agents = self.target / "AGENTS.md"
        existing = "# Consumer\n\nUse `.agents/agent-collaboration-kit/collaboration.md` when Lead is active.\n"
        agents.write_text(existing, encoding="utf-8")
        install(self.target)
        self.assertEqual(agents.read_text(encoding="utf-8"), existing)
        self.assertTrue((self.target / RELATIVE_DEST / "collaboration.md").exists())

    def test_symlink_target_is_not_followed(self):
        linked = Path(self.temp.name) / "linked"
        linked.symlink_to(self.target, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            install(linked)

    def test_external_protocol_reference_is_rejected_without_fallback(self):
        agents = self.target / "AGENTS.md"
        agents.write_text("Use `../other/.agents/agent-collaboration-kit/collaboration.md`.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside its own directory scope"):
            install(self.target)
        self.assertFalse((self.target / RELATIVE_DEST).exists())

    def test_absolute_protocol_reference_is_rejected(self):
        agents = self.target / "AGENTS.md"
        agents.write_text("Use `/another/project/.agent/collaboration.md`.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "outside its own directory scope"):
            install(self.target)


if __name__ == "__main__":
    unittest.main()
