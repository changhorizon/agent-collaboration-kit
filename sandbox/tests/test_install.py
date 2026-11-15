"""Ensure installation stays project-local and never overwrites existing protocols."""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

SANDBOX = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX.parent / "scripts"))
from install import (  # noqa: E402
    FILES,
    RELATIVE_DEST,
    SOURCE,
    STATE_FILES,
    TEMPLATES,
    VERSION_FILE,
    classify_upgrade,
    compute_source_version,
    install,
    package_source,
    read_installed_version,
    upgrade,
)


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def backup_dirs(target: Path) -> list[Path]:
    agents = target / ".agents"
    if not agents.is_dir():
        return []
    return sorted(
        path
        for path in agents.iterdir()
        if path.is_dir() and path.name.startswith("agent-collaboration-kit.backup-")
    )


class InstallChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SANDBOX)
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "consumer"
        self.target.mkdir()

    def install_kit(self) -> Path:
        install(self.target)
        return self.target / RELATIVE_DEST

    def write_runtime_fixture(self) -> dict[str, bytes]:
        agent = self.target / ".agent"
        (agent / "exchange/tasks").mkdir(parents=True)
        (agent / "exchange/tasks/task-1.md").write_text(
            "---\nid: fake-task\n---\nfake message\n", encoding="utf-8"
        )
        (agent / "decision-log.md").write_text(
            "# Local decisions\n\nDo not touch this runtime data.\n", encoding="utf-8"
        )
        (agent / "evidence").mkdir()
        (agent / "evidence/receipt.txt").write_text("evidence bytes\n", encoding="utf-8")
        return snapshot(agent)

    def test_dry_run_does_not_create_files(self):
        plan = install(self.target, dry_run=True)
        self.assertEqual(len(plan), len(FILES) + 2)
        self.assertIn(str(self.target / RELATIVE_DEST / VERSION_FILE), plan)
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

    def test_install_writes_version_stamp(self):
        destination = self.install_kit()
        version_file = destination / VERSION_FILE
        self.assertTrue(version_file.is_file())
        data = json.loads(version_file.read_text(encoding="utf-8"))
        self.assertEqual(
            sorted(data), ["installed_at", "source_commit", "source_dirty"]
        )
        expected = compute_source_version()
        self.assertEqual(data["source_commit"], expected["source_commit"])
        self.assertEqual(data["source_dirty"], expected["source_dirty"])
        installed_at = datetime.fromisoformat(data["installed_at"])
        self.assertIsNotNone(installed_at.tzinfo)
        self.assertEqual(installed_at.utcoffset().total_seconds(), 0)
        self.assertEqual(read_installed_version(destination), data)

    def test_source_version_degrades_when_git_is_unavailable(self):
        with mock.patch("install.subprocess.run", side_effect=FileNotFoundError):
            version = compute_source_version()
        self.assertEqual(
            version, {"source_commit": "unknown", "source_dirty": None}
        )

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

    def test_upgrade_requires_existing_installation(self):
        with self.assertRaisesRegex(ValueError, "first-time install"):
            upgrade(self.target, dry_run=True)
        self.assertFalse((self.target / ".agents").exists())

    def test_upgrade_requires_installed_version_stamp(self):
        destination = self.target / RELATIVE_DEST
        destination.mkdir(parents=True)
        (destination / "collaboration.md").write_text("old\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "installed version unknown"):
            upgrade(self.target, dry_run=True)

    def test_upgrade_classifies_add_unchanged_changed_and_preserve(self):
        destination = self.install_kit()
        (destination / "prompts/coder.md").unlink()
        (destination / "prompts/lead.md").write_text("custom lead\n", encoding="utf-8")
        (destination / "project-state.md").write_text("local state\n", encoding="utf-8")

        categories = classify_upgrade(destination)
        self.assertEqual(categories["add"], ["prompts/coder.md"])
        self.assertEqual(categories["changed"], ["prompts/lead.md"])
        self.assertIn("collaboration.md", categories["unchanged"])
        self.assertNotIn("prompts/lead.md", categories["unchanged"])
        self.assertEqual(categories["restore"], [])
        self.assertEqual(sorted(categories["preserve"]), sorted(STATE_FILES))

    def test_upgrade_dry_run_reports_everything_and_writes_nothing(self):
        destination = self.install_kit()
        (destination / "prompts/coder.md").unlink()
        (destination / "prompts/lead.md").write_text("custom lead\n", encoding="utf-8")
        (destination / "project-state.md").write_text("local state\n", encoding="utf-8")
        before = snapshot(self.target)

        report = upgrade(self.target, dry_run=True)

        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(backup_dirs(self.target))
        text = "\n".join(report)
        self.assertIn("installed version:", text)
        self.assertIn("target version:", text)
        self.assertIn("manifest add:", text)
        self.assertIn("manifest unchanged:", text)
        self.assertIn("manifest changed:", text)
        self.assertIn("manifest preserve:", text)
        self.assertIn("conflicts:", text)
        self.assertIn("version file:", text)
        self.assertIn("backup dir:", text)
        self.assertIn("backup files:", text)
        self.assertIn("rollback scope:", text)
        self.assertIn("STATE_FILES are not backed up", text)
        self.assertIn("consumer .agent/ runtime data is out of scope", text)
        self.assertIn("rollback:", text)
        self.assertIn("prompts/lead.md", text)
        self.assertIn("prompts/coder.md", text)

    def test_upgrade_without_conflicts_preserves_state_and_adds_missing_files(self):
        destination = self.install_kit()
        state = destination / "project-state.md"
        state.write_text("local state\n", encoding="utf-8")
        (destination / "prompts/coder.md").unlink()

        upgrade(self.target)

        self.assertEqual(state.read_text(encoding="utf-8"), "local state\n")
        self.assertTrue((destination / "prompts/coder.md").is_file())
        self.assertFalse(backup_dirs(self.target))

    def test_upgrade_refuses_changed_files_without_force(self):
        destination = self.install_kit()
        (destination / "prompts/lead.md").write_text("custom lead\n", encoding="utf-8")
        (destination / "project-state.md").write_text("local state\n", encoding="utf-8")
        before = snapshot(self.target)

        with self.assertRaisesRegex(ValueError, "conflicts"):
            upgrade(self.target)

        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(backup_dirs(self.target))

    def test_upgrade_force_backs_up_conflicts_and_preserves_state(self):
        destination = self.install_kit()
        lead = destination / "prompts/lead.md"
        lead.write_text("custom lead\n", encoding="utf-8")
        state = destination / "project-state.md"
        state.write_text("local state\n", encoding="utf-8")
        (destination / "prompts/coder.md").unlink()

        report = upgrade(self.target, force=True)

        report_text = "\n".join(report)
        self.assertIn("manifest changed: prompts/lead.md", report_text)
        self.assertIn("rollback scope:", report_text)
        self.assertIn("STATE_FILES are not backed up", report_text)
        self.assertIn("consumer .agent/ runtime data is out of scope", report_text)
        self.assertEqual(lead.read_bytes(), package_source("prompts/lead.md").read_bytes())
        self.assertTrue((destination / "prompts/coder.md").is_file())
        self.assertEqual(state.read_text(encoding="utf-8"), "local state\n")
        backups = backup_dirs(self.target)
        self.assertEqual(len(backups), 1)
        backup = backups[0]
        self.assertEqual(
            (backup / "prompts/lead.md").read_text(encoding="utf-8"), "custom lead\n"
        )
        self.assertFalse((backup / "project-state.md").exists())
        self.assertIsNotNone(read_installed_version(destination))

    def test_upgrade_uses_explicit_backup_dir_inside_agents(self):
        destination = self.install_kit()
        (destination / "prompts/lead.md").write_text("custom\n", encoding="utf-8")
        upgrade(self.target, force=True, backup_dir=".agents/manual-backup")
        backup = self.target / ".agents/manual-backup"
        self.assertTrue((backup / "prompts/lead.md").is_file())
        self.assertEqual(
            (backup / "prompts/lead.md").read_text(encoding="utf-8"), "custom\n"
        )

    def test_upgrade_rejects_backup_dir_outside_agents(self):
        destination = self.install_kit()
        (destination / "prompts/lead.md").write_text("custom\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "inside the target .agents"):
            upgrade(self.target, force=True, backup_dir=self.target / "backups")
        self.assertEqual(
            (destination / "prompts/lead.md").read_text(encoding="utf-8"), "custom\n"
        )
        self.assertFalse((self.target / "backups").exists())

    def test_upgrade_staging_failure_leaves_install_untouched(self):
        destination = self.install_kit()
        (destination / "prompts/lead.md").write_text("custom lead\n", encoding="utf-8")
        before = snapshot(self.target)

        with mock.patch("install.shutil.copy2", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                upgrade(self.target, force=True)

        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(backup_dirs(self.target))

    def test_upgrade_rejects_symlink_state_file(self):
        destination = self.install_kit()
        state = destination / "project-state.md"
        external = Path(self.temp.name) / "external-state.md"
        external.write_text("external state\n", encoding="utf-8")
        state.unlink()
        state.symlink_to(external)
        before = snapshot(self.target)

        with self.assertRaisesRegex(ValueError, "not a regular file.*replace or delete"):
            upgrade(self.target, force=True)

        self.assertEqual(snapshot(self.target), before)
        self.assertTrue(state.is_symlink())
        self.assertEqual(external.read_text(encoding="utf-8"), "external state\n")
        self.assertFalse(backup_dirs(self.target))

    def test_upgrade_rejects_directory_state_file_without_removing_it(self):
        destination = self.install_kit()
        state = destination / "project-state.md"
        state.unlink()
        state.mkdir()
        child = state / "keep.txt"
        child.write_text("keep\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "not a regular file.*replace or delete"):
            upgrade(self.target, force=True)

        self.assertTrue(state.is_dir())
        self.assertEqual(child.read_text(encoding="utf-8"), "keep\n")
        self.assertFalse(backup_dirs(self.target))

    def test_upgrade_restores_missing_state_file_from_template(self):
        destination = self.install_kit()
        state = destination / "project-state.md"
        state.unlink()
        before = snapshot(self.target)

        categories = classify_upgrade(destination)
        self.assertEqual(categories["restore"], ["project-state.md"])
        self.assertNotIn("project-state.md", categories["preserve"])

        report = upgrade(self.target, dry_run=True)
        text = "\n".join(report)
        self.assertIn(
            "manifest restore: project-state.md (状态文件缺失，将从空白模板安装)",
            text,
        )
        self.assertNotIn("manifest preserve: project-state.md", text)
        self.assertEqual(snapshot(self.target), before)

        upgrade(self.target)
        self.assertTrue(state.is_file())
        self.assertEqual(state.read_bytes(), (TEMPLATES / "project-state.md").read_bytes())

    def test_upgrade_rejects_linked_package_source(self):
        destination = self.install_kit()
        linked = Path(self.temp.name) / "linked-lead.md"
        linked.symlink_to(package_source("prompts/lead.md"))
        original_source = package_source

        def linked_source(relative: str) -> Path:
            if relative == "prompts/lead.md":
                return linked
            return original_source(relative)

        before = snapshot(self.target)
        with mock.patch("install.package_source", side_effect=linked_source):
            with self.assertRaisesRegex(ValueError, "missing or linked package source"):
                upgrade(self.target, force=True)

        self.assertEqual(snapshot(self.target), before)
        self.assertFalse(backup_dirs(self.target))

    def test_upgrade_failure_after_backup_reports_retained_backup(self):
        destination = self.install_kit()
        lead = destination / "prompts/lead.md"
        lead.write_text("custom lead\n", encoding="utf-8")
        (self.target / "AGENTS.md").unlink()

        with mock.patch("install._append_entry", side_effect=OSError("entry boom")):
            with self.assertRaisesRegex(ValueError, "backups retained at") as caught:
                upgrade(self.target, force=True)

        backup = caught.exception.backup_dir
        self.assertIsNotNone(backup)
        self.assertTrue((backup / "prompts/lead.md").is_file())
        self.assertEqual(
            (backup / "prompts/lead.md").read_text(encoding="utf-8"), "custom lead\n"
        )
        self.assertEqual(lead.read_text(encoding="utf-8"), "custom lead\n")

    def test_install_and_upgrade_never_touch_runtime_agent_directory(self):
        runtime_before = self.write_runtime_fixture()
        install(self.target)
        self.assertEqual(snapshot(self.target / ".agent"), runtime_before)

        destination = self.target / RELATIVE_DEST
        (destination / "prompts/lead.md").write_text("custom lead\n", encoding="utf-8")
        (destination / "project-state.md").write_text("custom state\n", encoding="utf-8")
        upgrade(self.target, force=True)
        self.assertEqual(snapshot(self.target / ".agent"), runtime_before)
        self.assertEqual(
            (self.target / ".agent/decision-log.md").read_text(encoding="utf-8"),
            "# Local decisions\n\nDo not touch this runtime data.\n",
        )
        self.assertTrue((self.target / ".agent/exchange/tasks/task-1.md").is_file())

    def test_upgrade_does_not_duplicate_agents_entry(self):
        agents = self.target / "AGENTS.md"
        existing = "# Consumer\n\nUse `.agents/agent-collaboration-kit/collaboration.md`.\n"
        agents.write_text(existing, encoding="utf-8")
        install(self.target)
        upgrade(self.target)
        self.assertEqual(agents.read_text(encoding="utf-8"), existing)

    def test_upgrade_refuses_modified_agents_pointer_without_local_reference(self):
        self.install_kit()
        agents = self.target / "AGENTS.md"
        agents.write_text(
            "# Consumer\n\nagent-collaboration-kit is configured elsewhere.\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "merge manually"):
            upgrade(self.target, dry_run=True)


if __name__ == "__main__":
    unittest.main()
