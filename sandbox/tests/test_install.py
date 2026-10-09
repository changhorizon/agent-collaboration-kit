"""Ensure installation stays project-local and never overwrites existing protocols."""

import sys
import tempfile
import unittest
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX.parent / "scripts"))
from install import (  # noqa: E402
    FILES,
    RELATIVE_DEST,
    SOURCE,
    STATE_FILES,
    TEMPLATES,
    install,
    package_source,
)


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

    def test_state_files_are_installed_from_blank_templates(self):
        install(self.target)
        destination = self.target / RELATIVE_DEST
        live_state = SANDBOX.parent / ".agent/project-state.md"
        live_is_filled = False
        for relative in STATE_FILES:
            installed = destination / relative
            template = TEMPLATES / relative
            self.assertTrue(template.is_file(), relative)
            self.assertEqual(installed.read_bytes(), template.read_bytes(), relative)
            self.assertNotIn(str(SANDBOX.parent.resolve()), installed.read_text(encoding="utf-8"))
            if relative == "project-state.md" and live_state.is_file():
                live_is_filled = live_state.read_bytes() != template.read_bytes()
        # When the live runtime state is filled locally, the installed copy must
        # still be the blank template and never mirror that live state.
        if live_is_filled:
            self.assertNotEqual(
                (destination / "project-state.md").read_bytes(), live_state.read_bytes()
            )

    def test_blank_templates_are_repository_independent(self):
        for relative in STATE_FILES:
            template = TEMPLATES / relative
            self.assertTrue(template.is_file(), relative)
            self.assertNotIn(
                str(SANDBOX.parent.resolve()), template.read_text(encoding="utf-8"), relative
            )

    def test_package_source_routes_state_files_to_templates(self):
        # Structural guard for W-1a. On a clean checkout the live .agent/ state
        # files are byte-identical to their blank templates, so content
        # assertions cannot tell the two sources apart. Assert the routing
        # directly: state files must resolve under TEMPLATES (never SOURCE),
        # and non-state files must still resolve under SOURCE.
        self.assertNotEqual(TEMPLATES, SOURCE)
        for relative in STATE_FILES:
            self.assertEqual(package_source(relative), TEMPLATES / relative, relative)
        self.assertEqual(package_source("collaboration.md"), SOURCE / "collaboration.md")

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
