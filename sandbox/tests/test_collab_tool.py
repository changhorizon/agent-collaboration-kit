"""Negative and concurrency tests for the explicit local collaboration tool."""

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[1]
KIT = SANDBOX.parent
sys.path.insert(0, str(KIT / "scripts"))
import collab  # noqa: E402


def message_text(
    task="TASK-T",
    message_id="M001",
    sender="lead",
    recipient="advisor",
    kind="request",
    created_at="2026-01-01T00:00:00Z",
    cwd="/workspace/example-project",
    object_ref="sample-object",
    version_ref="candidate-a",
    reply_to="null",
    supersedes="null",
    body=None,
    status="active",
):
    if body is None:
        if kind in {"request", "delegation"}:
            body = f"## 指令状态\n{status}\n\n## 目标\n测试目标。\n"
        elif kind == "review":
            body = "## 判定\nFAIL\n\n## 审阅角色与范围\nValidator：局部验收\n"
        elif kind == "advice":
            body = "## 推荐\n测试建议。\n"
        elif kind == "received":
            body = "## 接手\n已读取请求。\n"
        else:
            body = "## 实际结果与差异\n测试结果。\n"
    return f"""---
id: {message_id}
task: {task}
from: {sender}
to: {recipient}
kind: {kind}
created_at: {created_at}
cwd: {cwd}
object_ref: {object_ref}
version_ref: {version_ref}
reply_to: {reply_to}
supersedes: {supersedes}
---

{body}"""


def write_message(task_dir, filename, **kwargs):
    messages = Path(task_dir) / "messages"
    messages.mkdir(parents=True, exist_ok=True)
    path = messages / filename
    path.write_text(message_text(**kwargs), encoding="utf-8")
    return path


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SANDBOX)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.task_dir = self.root / "TASK-T"
        self.task_dir.mkdir()
        self.input = self.root / "draft.md"
        self.input.write_text(message_text(), encoding="utf-8")

    def fixed(self, prefix):
        return "lead-fixed001"

    def test_publish_generates_id_and_writes_valid_message(self):
        result = collab.publish(self.input, task_dir=self.task_dir, id_factory=self.fixed)
        path = Path(result["path"])
        self.assertTrue(path.is_file())
        self.assertEqual(result["id"], "lead-fixed001")
        self.assertEqual(result["task"], "TASK-T")
        parsed = collab.parse_message(path)
        self.assertEqual(parsed.header["id"], "lead-fixed001")
        self.assertEqual(parsed.header["from"], "lead")
        self.assertEqual(result["directory_validation"]["errors"], [])
        check = subprocess.run(
            [sys.executable, "-B", str(KIT / "sandbox" / "verify_messages.py"), str(self.task_dir / "messages")],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_publish_accepts_quoted_sender_like_the_parser(self):
        self.input.write_text(
            message_text().replace("from: lead", 'from: "lead"', 1), encoding="utf-8"
        )
        result = collab.publish(self.input, task_dir=self.task_dir, id_factory=self.fixed)
        self.assertEqual(result["from"], "lead")
        self.assertEqual(collab.parse_message(Path(result["path"])).header["from"], "lead")

    def test_publish_refuses_existing_id_and_does_not_rewrite_original(self):
        first = collab.publish(self.input, task_dir=self.task_dir, id_factory=self.fixed)
        original = Path(first["path"]).read_bytes()
        with self.assertRaises(collab.CollabError):
            collab.publish(self.input, task_dir=self.task_dir, id_factory=self.fixed)
        self.assertEqual(Path(first["path"]).read_bytes(), original)

    def test_publish_refuses_existing_id_under_another_filename(self):
        messages = self.task_dir / "messages"
        messages.mkdir()
        (messages / "manual.md").write_text(
            message_text(message_id="lead-fixed001"), encoding="utf-8"
        )
        with self.assertRaises(collab.CollabError):
            collab.publish(self.input, task_dir=self.task_dir, id_factory=self.fixed)

    def test_invalid_message_writes_no_formal_message(self):
        self.input.write_text(message_text(sender="coder", kind="request"), encoding="utf-8")
        with self.assertRaises(collab.CollabError):
            collab.publish(self.input, task_dir=self.task_dir, id_factory=self.fixed)
        messages = self.task_dir / "messages"
        self.assertFalse(messages.exists() and list(messages.glob("*.md")))

    def test_concurrent_duplicate_publish_has_one_winner(self):
        barrier = threading.Barrier(2)
        successes = []
        failures = []

        def attempt():
            barrier.wait()
            try:
                successes.append(collab.publish(self.input, task_dir=self.task_dir, id_factory=self.fixed))
            except Exception as error:  # noqa: BLE001 - test records the loser
                failures.append(error)

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], collab.CollabError)
        self.assertEqual(len(list((self.task_dir / "messages").glob("*.md"))), 1)

    def _message_files(self):
        return sorted((self.task_dir / "messages").rglob("*.md"))

    def test_publish_rejects_missing_reply_target_without_writing(self):
        write_message(self.task_dir, "M001.md", message_id="M001", sender="lead", recipient="advisor")
        before = self._message_files()
        self.input.write_text(
            message_text(
                message_id="M002",
                reply_to="M999",
                created_at="2026-01-01T00:01:00Z",
            ),
            encoding="utf-8",
        )
        with self.assertRaises(collab.CollabError) as context:
            collab.publish(self.input, task_dir=self.task_dir, id_factory=self.fixed)
        self.assertIn("directory-level validation failed", str(context.exception))
        self.assertEqual(self._message_files(), before)

    def test_publish_rejects_cross_author_supersede_without_writing(self):
        write_message(
            self.task_dir,
            "M001.md",
            message_id="M001",
            sender="validator",
            recipient="lead",
            kind="review",
        )
        before = self._message_files()
        self.input.write_text(
            message_text(
                message_id="M002",
                sender="reviewer",
                recipient="lead",
                kind="review",
                created_at="2026-01-01T00:01:00Z",
                supersedes="M001",
            ),
            encoding="utf-8",
        )
        with self.assertRaises(collab.CollabError) as context:
            collab.publish(self.input, task_dir=self.task_dir, id_factory=self.fixed)
        self.assertIn("supersedes must keep kind and author", str(context.exception))
        self.assertEqual(self._message_files(), before)

    def test_publish_rejects_existing_directory_duplicate_ids_without_writing(self):
        first = write_message(
            self.task_dir, "M001.md", message_id="M001", sender="lead", recipient="advisor"
        )
        shutil.copyfile(first, first.with_name("duplicate.md"))
        before = self._message_files()
        self.input.write_text(
            message_text(message_id="M100", created_at="2026-01-01T00:01:00Z"),
            encoding="utf-8",
        )
        with self.assertRaises(collab.CollabError) as context:
            collab.publish(self.input, task_dir=self.task_dir, id_factory=self.fixed)
        self.assertIn("duplicate message ID", str(context.exception))
        self.assertEqual(self._message_files(), before)

    def test_publish_directory_invalid_does_not_create_message_directory(self):
        self.input.write_text(
            message_text(reply_to="M999", created_at="2026-01-01T00:01:00Z"),
            encoding="utf-8",
        )
        with self.assertRaises(collab.CollabError):
            collab.publish(self.input, task_dir=self.task_dir, id_factory=self.fixed)
        self.assertFalse((self.task_dir / "messages").exists())


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SANDBOX)
        self.addCleanup(self.temp.cleanup)
        self.task_dir = Path(self.temp.name) / "TASK-L"
        self.task_dir.mkdir()

    def init(self, quota):
        return collab.ledger_init(
            task_dir=self.task_dir, quota=quota, baseline_ref="user-approval-001"
        )

    def test_check_unknown_ledger_does_not_guess(self):
        report = collab.ledger_check(ledger=Path(self.temp.name) / "missing.json")
        self.assertEqual(report["status"], "unknown")
        self.assertIn("not a runtime gate", report["note"])

    def test_init_refuses_overwrite(self):
        self.init({"coder": 1})
        with self.assertRaises(collab.CollabError):
            self.init({"coder": 1})

    def test_concurrent_reservations_for_last_slot_have_one_winner(self):
        self.init({"coder": 1})
        barrier = threading.Barrier(2)
        successes = []
        failures = []

        def attempt(call_ref):
            barrier.wait()
            try:
                successes.append(collab.ledger_reserve("coder", call_ref, task_dir=self.task_dir))
            except Exception as error:  # noqa: BLE001 - test records the loser
                failures.append(error)

        threads = [threading.Thread(target=attempt, args=(name,)) for name in ("call-1", "call-2")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], collab.CollabError)
        report = collab.ledger_check(task_dir=self.task_dir)
        self.assertEqual(report["roles"]["coder"]["reserved"], 1)
        self.assertEqual(report["roles"]["coder"]["remaining"], 0)

    def test_reserve_is_idempotent_for_same_call_ref(self):
        self.init({"coder": 2})
        first = collab.ledger_reserve("coder", "call-1", task_dir=self.task_dir)
        second = collab.ledger_reserve("coder", "call-1", task_dir=self.task_dir)
        self.assertEqual(first["status"], "reserved")
        self.assertEqual(second["status"], "duplicate")
        report = collab.ledger_check(task_dir=self.task_dir)
        self.assertEqual(report["roles"]["coder"]["reserved"], 1)
        self.assertEqual(report["roles"]["coder"]["remaining"], 1)

    def test_release_only_unstarted_reservation_and_no_refund_for_consumed(self):
        self.init({"coder": 2})
        collab.ledger_reserve("coder", "call-1", task_dir=self.task_dir)
        released = collab.ledger_release("coder", "call-1", task_dir=self.task_dir)
        self.assertEqual(released["status"], "released")

        collab.ledger_reserve("coder", "call-2", task_dir=self.task_dir)
        collab.ledger_settle("coder", "call-2", status="settled", task_dir=self.task_dir)
        with self.assertRaises(collab.CollabError):
            collab.ledger_release("coder", "call-2", task_dir=self.task_dir)
        report = collab.ledger_check(task_dir=self.task_dir)
        self.assertEqual(report["roles"]["coder"]["settled"], 1)
        self.assertEqual(report["roles"]["coder"]["released"], 1)
        self.assertEqual(report["roles"]["coder"]["remaining"], 1)

    def test_started_reservation_cannot_be_released(self):
        self.init({"coder": 1})
        collab.ledger_reserve("coder", "call-1", task_dir=self.task_dir)
        collab.ledger_settle("coder", "call-1", status="started", task_dir=self.task_dir)
        with self.assertRaises(collab.CollabError):
            collab.ledger_release("coder", "call-1", task_dir=self.task_dir)

    def test_unknown_role_and_over_budget_are_refused_locally(self):
        self.init({"coder": 1})
        with self.assertRaises(collab.CollabError):
            collab.ledger_reserve("validator", "call-x", task_dir=self.task_dir)
        collab.ledger_reserve("coder", "call-1", task_dir=self.task_dir)
        with self.assertRaises(collab.CollabError):
            collab.ledger_reserve("coder", "call-2", task_dir=self.task_dir)

    def test_malformed_ledger_is_reported_unknown(self):
        ledger = self.task_dir / "budget.json"
        ledger.write_text('{"schema": "collab-ledger/1", "entries": []}', encoding="utf-8")
        report = collab.ledger_check(ledger=ledger)
        self.assertEqual(report["status"], "unknown")
        self.assertIn("unknown", report["reason"])


class PreserveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SANDBOX)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / "project"
        (self.base / "src").mkdir(parents=True)
        (self.base / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
        (self.base / "untracked.txt").write_text("new delivery\n", encoding="utf-8")
        (self.base / ".env").write_text("SECRET=1\n", encoding="utf-8")
        (self.base / "__pycache__").mkdir()
        (self.base / "__pycache__" / "cache.pyc").write_bytes(b"cache")

    def test_manifest_identity_excludes_and_deleted_marker(self):
        manifest = collab.preserve_manifest(
            self.base,
            files=["src/app.py", "missing.py"],
            untracked=["untracked.txt"],
            want_sha256=True,
        )
        paths = {item["path"]: item for item in manifest["files"]}
        self.assertIn("src/app.py", paths)
        self.assertIn("untracked.txt", paths)
        self.assertTrue(paths["missing.py"]["deleted"])
        self.assertNotIn(".env", paths)
        self.assertNotIn("__pycache__/cache.pyc", paths)
        expected = hashlib.sha256((self.base / "src" / "app.py").read_bytes()).hexdigest()
        self.assertEqual(paths["src/app.py"]["sha256"], expected)
        self.assertEqual(paths["untracked.txt"]["declared_as"], "untracked")
        self.assertIn("manifest_sha256", manifest)

    def test_manifest_out_then_verify_detects_changed_candidate(self):
        out = self.root / "manifest.json"
        collab.preserve_manifest(self.base, files=["src/app.py"], out=out, want_sha256=True)
        initial = collab.verify_manifest(out)
        self.assertIn(initial["status"], {"ok", "ok-with-unknown-baseline"})
        self.assertEqual(initial["mismatches"], [])
        (self.base / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
        result = collab.verify_manifest(out)
        self.assertEqual(result["status"], "mismatch")
        mismatched = {item["path"] for item in result["mismatches"]}
        self.assertIn("src/app.py", mismatched)
        self.assertTrue(any("sha256 mismatch" in item["reason"] for item in result["mismatches"]))

    def test_verify_missing_declared_file_is_a_mismatch(self):
        out = self.root / "manifest-missing.json"
        collab.preserve_manifest(
            self.base, files=["src/app.py", "untracked.txt"], out=out, want_sha256=True
        )
        (self.base / "untracked.txt").unlink()
        result = collab.verify_manifest(out)
        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(
            any(
                item["path"] == "untracked.txt" and item["reason"] == "missing"
                for item in result["mismatches"]
            )
        )

    def test_verify_detects_git_head_change_without_candidate_change(self):
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        base = self.root / "git-project"
        base.mkdir()
        (base / "app.py").write_text("ok\n", encoding="utf-8")
        self._git(base, "init", "-q")
        self._git(base, "add", "app.py")
        self._git(
            base, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-q", "-m", "one",
        )
        out = self.root / "manifest-git.json"
        collab.preserve_manifest(base, files=["app.py"], out=out, want_sha256=True)
        recorded = json.loads(out.read_text(encoding="utf-8"))["base_identity"]
        self.assertTrue(recorded["git_available"])
        (base / "other.txt").write_text("other\n", encoding="utf-8")
        self._git(base, "add", "other.txt")
        self._git(
            base, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-q", "-m", "two",
        )
        result = collab.verify_manifest(out)
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(result["git_identity"]["status"], "mismatch")
        self.assertTrue(any("git HEAD mismatch" in item["reason"] for item in result["mismatches"]))

    def test_verify_marks_missing_git_baseline_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (base / "app.py").write_text("ok\n", encoding="utf-8")
            out = base / "manifest.json"
            collab.preserve_manifest(base, files=["app.py"], out=out, want_sha256=True)
            if collab._git_metadata(base)["available"]:
                self.skipTest("temporary base is unexpectedly inside a Git worktree")
            result = collab.verify_manifest(out)
            self.assertEqual(result["status"], "ok-with-unknown-baseline")
            self.assertEqual(result["git_identity"]["status"], "unknown")
            self.assertEqual(result["mismatches"], [])

    def _git(self, base, *arguments):
        subprocess.run(
            ["git", "-C", str(base), *arguments],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_archive_copies_bytes_and_records_transcriber_not_author(self):
        source = self.root / "coder-return.md"
        source.write_text("原始返回内容\n", encoding="utf-8")
        evidence = self.root / "evidence"
        result = collab.preserve_archive(
            source,
            original_author="coder",
            transcribed_by="lead",
            call_ref="call-001",
            version="candidate-a",
            redaction="none",
            out=evidence,
        )
        archived = Path(result["archived_file"])
        self.assertEqual(archived.read_bytes(), source.read_bytes())
        metadata = json.loads(Path(result["metadata"]).read_text(encoding="utf-8"))
        self.assertEqual(metadata["original_author"], "coder")
        self.assertEqual(metadata["transcribed_by"], "lead")
        self.assertNotEqual(metadata["original_author"], metadata["transcribed_by"])
        self.assertEqual(metadata["content_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        with self.assertRaises(collab.CollabError):
            collab.preserve_archive(
                source,
                original_author="coder",
                transcribed_by="lead",
                call_ref="call-002",
                version="candidate-a",
                out=evidence,
            )
        self.assertEqual(archived.read_bytes(), source.read_bytes())

    def test_archive_refuses_overwrite_of_metadata(self):
        source = self.root / "coder-return.md"
        source.write_text("原始返回内容\n", encoding="utf-8")
        evidence = self.root / "evidence"
        collab.preserve_archive(
            source,
            original_author="coder",
            transcribed_by="lead",
            call_ref="call-001",
            version="candidate-a",
            out=evidence,
        )
        metadata = evidence / (source.name + ".meta.json")
        before = metadata.read_bytes()
        with self.assertRaises(collab.CollabError):
            collab.preserve_archive(
                source,
                original_author="coder",
                transcribed_by="validator",
                call_ref="call-003",
                version="candidate-b",
                out=evidence,
            )
        self.assertEqual(metadata.read_bytes(), before)

    def test_archive_missing_source_is_refused_without_evidence(self):
        missing = self.root / "missing-return.md"
        evidence = self.root / "evidence-missing"
        with self.assertRaises(collab.CollabError):
            collab.preserve_archive(
                missing,
                original_author="coder",
                transcribed_by="lead",
                call_ref="call-missing",
                version="candidate-a",
                out=evidence,
            )
        self.assertFalse(evidence.exists())


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SANDBOX)
        self.addCleanup(self.temp.cleanup)
        self.task_dir = Path(self.temp.name) / "TASK-S"

    def state(self):
        return collab.derive_state(self.task_dir)

    def test_supersede_chain_keeps_old_technical_body_and_confirms_receipt(self):
        write_message(self.task_dir, "M001.md", message_id="M001", sender="lead", recipient="advisor")
        write_message(
            self.task_dir,
            "M002.md",
            message_id="M002",
            sender="advisor",
            recipient="lead",
            kind="received",
            created_at="2026-01-01T00:01:00Z",
            reply_to="M001",
        )
        write_message(
            self.task_dir,
            "M003.md",
            message_id="M003",
            sender="advisor",
            recipient="lead",
            kind="advice",
            created_at="2026-01-01T00:02:00Z",
            reply_to="M001",
        )
        write_message(
            self.task_dir,
            "M004.md",
            message_id="M004",
            sender="lead",
            recipient="advisor",
            created_at="2026-01-01T00:03:00Z",
            reply_to="M003",
        )
        write_message(
            self.task_dir,
            "M005.md",
            message_id="M005",
            sender="advisor",
            recipient="lead",
            kind="advice",
            created_at="2026-01-01T00:04:00Z",
            reply_to="M004",
            supersedes="M003",
        )
        state = self.state()
        current = {entry["id"] for entry in state["entries"] if entry["status"] == "current"}
        self.assertIn("M005", current)
        self.assertNotIn("M003", current)
        entry = next(item for item in state["entries"] if item["id"] == "M005")
        self.assertIn("M003", {item["id"] for item in entry["superseded_ancestors"]})
        self.assertTrue(any(item["id"] == "M003" for item in state["superseded_history"]))
        delivery = next(item for item in state["delivery"] if item["id"] == "M001")
        self.assertEqual(delivery["status"], "confirmed")
        notices = {item["id"] for item in state["executable_notices"]}
        self.assertIn("M005", notices)
        self.assertNotIn("M003", notices)

    def test_missing_received_is_unconfirmed_not_unread_proof(self):
        write_message(self.task_dir, "M001.md", message_id="M001", sender="lead", recipient="advisor")
        state = self.state()
        delivery = next(item for item in state["delivery"] if item["id"] == "M001")
        self.assertEqual(delivery["status"], "unconfirmed")
        self.assertIn("not proof of non-delivery", delivery["note"])

    def test_cancellation_does_not_revive_ancestor(self):
        write_message(self.task_dir, "M001.md", message_id="M001", sender="lead", recipient="advisor")
        write_message(
            self.task_dir,
            "M002.md",
            message_id="M002",
            sender="lead",
            recipient="advisor",
            status="cancelled",
            created_at="2026-01-01T00:01:00Z",
            reply_to="M001",
            supersedes="M001",
        )
        state = self.state()
        current = {entry["id"] for entry in state["entries"] if entry["status"] == "current"}
        self.assertNotIn("M001", current)
        entry = next(item for item in state["entries"] if item["id"] == "M002")
        self.assertEqual(entry["status"], "cancelled")
        self.assertTrue(any(item["id"] == "M001" for item in state["superseded_history"]))
        notices = {item["id"] for item in state["executable_notices"]}
        self.assertNotIn("M001", notices)
        self.assertNotIn("M002", notices)

    def test_multiple_successors_suppress_notices_but_not_unrelated_chain(self):
        write_message(
            self.task_dir,
            "M010.md",
            message_id="M010",
            sender="advisor",
            recipient="lead",
            kind="advice",
            created_at="2026-01-01T00:00:00Z",
        )
        write_message(
            self.task_dir,
            "M011.md",
            message_id="M011",
            sender="advisor",
            recipient="lead",
            kind="advice",
            created_at="2026-01-01T00:01:00Z",
            reply_to="M010",
            supersedes="M010",
        )
        write_message(
            self.task_dir,
            "M012.md",
            message_id="M012",
            sender="advisor",
            recipient="lead",
            kind="advice",
            created_at="2026-01-01T00:02:00Z",
            reply_to="M010",
            supersedes="M010",
        )
        write_message(
            self.task_dir,
            "M100.md",
            message_id="M100",
            sender="lead",
            recipient="advisor",
            created_at="2026-01-01T00:03:00Z",
        )
        state = self.state()
        self.assertTrue(any(item["kind"] == "multiple_successors" for item in state["conflicts"]))
        notices = {item["id"] for item in state["executable_notices"]}
        self.assertNotIn("M011", notices)
        self.assertNotIn("M012", notices)
        self.assertIn("M100", notices)

    def test_duplicate_id_is_a_conflict_and_suppresses_that_notice(self):
        first = write_message(self.task_dir, "M001.md", message_id="M001", sender="lead", recipient="advisor")
        shutil.copyfile(first, first.with_name("duplicate.md"))
        state = self.state()
        self.assertTrue(any(item["kind"] == "duplicate_id" for item in state["conflicts"]))
        entry = next(item for item in state["entries"] if item["id"] == "M001")
        self.assertEqual(entry["status"], "conflict")
        self.assertNotIn("M001", {item["id"] for item in state["executable_notices"]})

    def test_cycle_is_a_conflict_and_suppresses_notices(self):
        write_message(
            self.task_dir,
            "M020.md",
            message_id="M020",
            sender="advisor",
            recipient="lead",
            kind="advice",
            created_at="2026-01-01T00:00:00Z",
        )
        write_message(
            self.task_dir,
            "M021.md",
            message_id="M021",
            sender="advisor",
            recipient="lead",
            kind="advice",
            created_at="2026-01-01T00:01:00Z",
            reply_to="M020",
            supersedes="M020",
        )
        (self.task_dir / "messages" / "M020.md").write_text(
            message_text(
                message_id="M020",
                sender="advisor",
                recipient="lead",
                kind="advice",
                created_at="2026-01-01T00:00:00Z",
                supersedes="M021",
            ),
            encoding="utf-8",
        )
        state = self.state()
        self.assertTrue(state["cycles"])
        self.assertTrue(any(item["kind"] == "reference_cycle" for item in state["conflicts"]))
        self.assertFalse({item["id"] for item in state["executable_notices"]} & {"M020", "M021"})

    def test_missing_supersede_reference_is_a_conflict(self):
        write_message(
            self.task_dir,
            "M030.md",
            message_id="M030",
            sender="advisor",
            recipient="lead",
            kind="advice",
            supersedes="M999",
        )
        state = self.state()
        self.assertTrue(state["reference_gaps"])
        self.assertEqual(state["entries"][0]["status"], "conflict")
        self.assertNotIn("M030", {item["id"] for item in state["executable_notices"]})

    def test_cross_author_supersede_is_a_conflict(self):
        write_message(
            self.task_dir,
            "M050.md",
            message_id="M050",
            sender="validator",
            recipient="lead",
            kind="review",
            created_at="2026-01-01T00:00:00Z",
        )
        write_message(
            self.task_dir,
            "M051.md",
            message_id="M051",
            sender="reviewer",
            recipient="lead",
            kind="review",
            created_at="2026-01-01T00:01:00Z",
            reply_to="M050",
            supersedes="M050",
        )
        state = self.state()
        self.assertTrue(any(item["kind"] == "cross_author_supersede" for item in state["conflicts"]))
        self.assertFalse({item["id"] for item in state["executable_notices"]} & {"M050", "M051"})

    def test_executability_remains_unknown(self):
        write_message(self.task_dir, "M001.md", message_id="M001", sender="lead", recipient="advisor")
        state = self.state()
        self.assertEqual(state["executability"]["authorization"], "unknown")
        self.assertEqual(state["executability"]["budget"], "unknown")
        self.assertEqual(state["executability"]["pause"], "unknown")


class CliExitCodeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SANDBOX)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.script = KIT / "scripts" / "collab.py"

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-B", str(self.script), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )

    def _git(self, base, *arguments):
        subprocess.run(
            ["git", "-C", str(base), *arguments],
            capture_output=True,
            text=True,
            check=True,
        )

    def test_publish_success_and_invalid_input_exit_codes(self):
        task_dir = self.root / "TASK-CLI"
        task_dir.mkdir()
        draft = self.root / "draft.md"
        draft.write_text(message_text(), encoding="utf-8")
        success = self.run_cli("publish", str(draft), "--task-dir", str(task_dir))
        self.assertEqual(success.returncode, 0, success.stderr)
        payload = json.loads(success.stdout)
        self.assertTrue(Path(payload["path"]).is_file())
        self.assertIn("NOT verified", payload["validation"])
        self.assertEqual(payload["directory_validation"]["errors"], [])

        draft.write_text(message_text(sender="coder", kind="request"), encoding="utf-8")
        failure = self.run_cli("publish", str(draft), "--task-dir", str(task_dir))
        self.assertNotEqual(failure.returncode, 0)
        self.assertIn("validation failed", failure.stderr)

    def test_ledger_over_budget_exits_non_zero_with_local_refusal_wording(self):
        task_dir = self.root / "TASK-CLI"
        task_dir.mkdir()
        init = self.run_cli("ledger", "init", "--task-dir", str(task_dir), "--quota", "coder=1")
        self.assertEqual(init.returncode, 0, init.stderr)
        first = self.run_cli("ledger", "reserve", "coder", "call-1", "--task-dir", str(task_dir))
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.run_cli("ledger", "reserve", "coder", "call-2", "--task-dir", str(task_dir))
        self.assertNotEqual(second.returncode, 0)
        self.assertIn("local tool refusal", second.stderr)
        self.assertIn("not proof of a runtime gate", second.stderr)

    def test_manifest_verify_mismatch_exits_one(self):
        base = self.root / "project"
        base.mkdir()
        (base / "app.py").write_text("ok\n", encoding="utf-8")
        manifest = self.root / "manifest.json"
        build = self.run_cli(
            "preserve",
            "manifest",
            "--base",
            str(base),
            "--files",
            "app.py",
            "--out",
            str(manifest),
            "--sha256",
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        (base / "app.py").write_text("changed\n", encoding="utf-8")
        verify = self.run_cli("preserve", "manifest", "--verify", str(manifest))
        self.assertEqual(verify.returncode, 1, verify.stderr)
        payload = json.loads(verify.stdout)
        self.assertEqual(payload["status"], "mismatch")
        self.assertTrue(any(item["reason"] == "sha256 mismatch" for item in payload["mismatches"]))

    def test_publish_directory_invalid_message_exits_non_zero_without_writing(self):
        task_dir = self.root / "TASK-CLI-DIR"
        task_dir.mkdir()
        write_message(task_dir, "M001.md", message_id="M001", sender="lead", recipient="advisor")
        before = sorted((task_dir / "messages").rglob("*.md"))
        draft = self.root / "draft-directory-invalid.md"
        draft.write_text(
            message_text(message_id="M002", reply_to="M999", created_at="2026-01-01T00:01:00Z"),
            encoding="utf-8",
        )
        result = self.run_cli("publish", str(draft), "--task-dir", str(task_dir))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("directory-level validation failed", result.stderr)
        self.assertEqual(sorted((task_dir / "messages").rglob("*.md")), before)

    def test_manifest_verify_missing_file_exits_one(self):
        base = self.root / "project-missing"
        base.mkdir()
        (base / "app.py").write_text("ok\n", encoding="utf-8")
        (base / "other.py").write_text("other\n", encoding="utf-8")
        manifest = self.root / "manifest-missing.json"
        build = self.run_cli(
            "preserve",
            "manifest",
            "--base",
            str(base),
            "--files",
            "app.py",
            "other.py",
            "--out",
            str(manifest),
            "--sha256",
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        (base / "other.py").unlink()
        verify = self.run_cli("preserve", "manifest", "--verify", str(manifest))
        self.assertEqual(verify.returncode, 1, verify.stderr)
        payload = json.loads(verify.stdout)
        self.assertEqual(payload["status"], "mismatch")
        self.assertTrue(
            any(
                item["path"] == "other.py" and item["reason"] == "missing"
                for item in payload["mismatches"]
            )
        )

    def test_archive_missing_source_exits_non_zero_without_evidence(self):
        evidence = self.root / "evidence-missing"
        result = self.run_cli(
            "preserve",
            "archive",
            "--return-file",
            str(self.root / "missing-return.md"),
            "--from",
            "coder",
            "--transcribed-by",
            "lead",
            "--call-ref",
            "call-missing",
            "--version",
            "candidate-a",
            "--out",
            str(evidence),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(evidence.exists())

    def test_ledger_check_unknown_and_over_exit_two(self):
        missing = self.run_cli("ledger", "check", "--ledger", str(self.root / "missing.json"))
        self.assertEqual(missing.returncode, 2)
        missing_payload = json.loads(missing.stdout)
        self.assertEqual(missing_payload["status"], "unknown")
        self.assertIn("status/remaining", missing_payload["decision_hint"])

        task_dir = self.root / "TASK-CLI-CHECK"
        task_dir.mkdir()
        init = self.run_cli("ledger", "init", "--task-dir", str(task_dir), "--quota", "coder=1")
        self.assertEqual(init.returncode, 0, init.stderr)
        ok = self.run_cli("ledger", "check", "--task-dir", str(task_dir))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertEqual(json.loads(ok.stdout)["status"], "ok")

        over_ledger = self.root / "budget-over.json"
        over_ledger.write_text(
            json.dumps(
                {
                    "schema": "collab-ledger/1",
                    "task_dir": str(task_dir),
                    "baseline_ref": "test-baseline",
                    "parent_scope": None,
                    "created_at": "2026-01-01T00:00:00Z",
                    "quota": {"coder": 1},
                    "entries": [
                        {
                            "call_ref": "call-1",
                            "role": "coder",
                            "status": "settled",
                            "reserved_at": "2026-01-01T00:00:00Z",
                            "updated_at": "2026-01-01T00:01:00Z",
                            "source": "test",
                            "transitions": [],
                        },
                        {
                            "call_ref": "call-2",
                            "role": "coder",
                            "status": "settled",
                            "reserved_at": "2026-01-01T00:02:00Z",
                            "updated_at": "2026-01-01T00:03:00Z",
                            "source": "test",
                            "transitions": [],
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        over = self.run_cli("ledger", "check", "--ledger", str(over_ledger))
        self.assertEqual(over.returncode, 2)
        over_payload = json.loads(over.stdout)
        self.assertEqual(over_payload["status"], "over")
        self.assertEqual(over_payload["roles"]["coder"]["status"], "over")
        self.assertEqual(over_payload["roles"]["coder"]["remaining"], -1)

    def test_manifest_verify_git_head_change_exits_one(self):
        if shutil.which("git") is None:
            self.skipTest("git is not installed")
        base = self.root / "git-cli"
        base.mkdir()
        (base / "app.py").write_text("ok\n", encoding="utf-8")
        self._git(base, "init", "-q")
        self._git(base, "add", "app.py")
        self._git(
            base, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-q", "-m", "one",
        )
        manifest = self.root / "manifest-git-cli.json"
        build = self.run_cli(
            "preserve",
            "manifest",
            "--base",
            str(base),
            "--files",
            "app.py",
            "--out",
            str(manifest),
            "--sha256",
        )
        self.assertEqual(build.returncode, 0, build.stderr)
        (base / "other.txt").write_text("other\n", encoding="utf-8")
        self._git(base, "add", "other.txt")
        self._git(
            base, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "-q", "-m", "two",
        )
        verify = self.run_cli("preserve", "manifest", "--verify", str(manifest))
        self.assertEqual(verify.returncode, 1, verify.stderr)
        payload = json.loads(verify.stdout)
        self.assertEqual(payload["status"], "mismatch")
        self.assertEqual(payload["git_identity"]["status"], "mismatch")
        self.assertTrue(any("git HEAD mismatch" in item["reason"] for item in payload["mismatches"]))


if __name__ == "__main__":
    unittest.main()
