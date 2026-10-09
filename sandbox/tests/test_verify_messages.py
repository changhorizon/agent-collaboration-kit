"""Exercise protocol failure cases without touching a consumer project."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SANDBOX = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SANDBOX))
from verify_messages import validate  # noqa: E402


class MessageChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=SANDBOX)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "messages"
        shutil.copytree(SANDBOX / "fixtures" / "messages", self.root)

    def edit(self, task: str, filename: str, old: str, new: str):
        path = self.root / task / "messages" / filename
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_valid_a3_revision_and_lead_requested_auditor_report(self):
        count, tasks, errors = validate(self.root)
        self.assertEqual((count, tasks, errors), (7, 2, []))

    def test_disposable_candidate_check_is_sensitive_to_change(self):
        workspace = Path(self.temp.name) / "project"
        shutil.copytree(SANDBOX / "fixtures" / "project", workspace)

        def run_check():
            return subprocess.run(
                [sys.executable, "-B", "-m", "unittest", "discover", "-s", str(workspace), "-p", "test_candidate.py"],
                capture_output=True,
                text=True,
                check=False,
            ).returncode

        self.assertNotEqual(run_check(), 0)  # Pending candidate: fails as expected.
        candidate = workspace / "candidate.txt"
        candidate.write_text("ready\n", encoding="utf-8")
        self.assertEqual(run_check(), 0)
        candidate.write_text("pending\n", encoding="utf-8")
        self.assertNotEqual(run_check(), 0)  # Negative probe: the check turns red again.

    def test_missing_reply_target_fails_closed(self):
        self.edit("TASK-DEMO", "M004-lead-a3-request.md", "reply_to: M003", "reply_to: M999")
        self.assertIn("reply_to target M999 missing", "\n".join(validate(self.root)[2]))

    def test_cycle_cannot_hide_in_correction_chain(self):
        self.edit("TASK-DEMO", "M005-advisor-revised-advice.md", "supersedes: M003", "supersedes: M005")
        self.assertIn("reference cycle", "\n".join(validate(self.root)[2]))

    def test_coder_advice_and_lead_authored_audit_are_not_accepted(self):
        self.edit("TASK-DEMO", "M003-advisor-advice.md", "from: advisor", "from: coder")
        self.edit("TASK-AUDIT", "M002-auditor-review.md", "from: auditor", "from: lead")
        errors = "\n".join(validate(self.root)[2])
        self.assertIn("only Advisor may issue advice", errors)
        self.assertIn("review must come from Validator, Reviewer or Auditor", errors)

    def test_advisor_can_request_audit_with_existing_user_mandate(self):
        self.edit("TASK-AUDIT", "M001-lead-audit-request.md", "from: lead", "from: advisor")
        self.assertEqual(validate(self.root)[2], [])  # Existing mandate is not structurally verifiable.

    def test_routine_auditor_report_must_address_lead(self):
        self.edit("TASK-AUDIT", "M002-auditor-review.md", "to: lead", "to: user")
        self.assertIn("Auditor user escalation requires ESCALATE", "\n".join(validate(self.root)[2]))

    def test_auditor_user_escalation_requires_reason(self):
        original = self.root / "TASK-AUDIT" / "messages" / "M002-auditor-review.md"
        escalation = original.with_name("M003-auditor-escalation.md")
        escalation.write_text(
            original.read_text(encoding="utf-8")
            .replace("id: M002", "id: M003", 1)
            .replace("to: lead", "to: user", 1)
            .replace("00:01:00Z", "00:02:00Z", 1)
            .replace("reply_to: M001", "reply_to: M002", 1)
            .replace("PASS WITH WARNINGS", "ESCALATE", 1),
            encoding="utf-8",
        )
        self.assertIn("requires ESCALATE and ## 升级原因", "\n".join(validate(self.root)[2]))
        self.edit(
            "TASK-AUDIT", "M003-auditor-escalation.md",
            "## 审阅角色与范围", "## 升级原因\n超出角色范围的用户授权边界。\n\n## 审阅角色与范围",
        )
        self.assertEqual(validate(self.root)[2], [])
        self.edit("TASK-AUDIT", "M003-auditor-escalation.md", "reply_to: M002", "reply_to: M001")
        self.assertIn("must reply to original review to Lead", "\n".join(validate(self.root)[2]))

    def test_subagent_result_cannot_claim_direct_user_delivery(self):
        self.edit("TASK-DEMO", "M002-advisor-received.md", "from: advisor", "from: coder")
        self.edit("TASK-DEMO", "M002-advisor-received.md", "to: lead", "to: user")
        self.assertIn("subagent output must be addressed to Lead", "\n".join(validate(self.root)[2]))

    def test_quoted_header_and_utc_offset_are_accepted(self):
        self.edit("TASK-DEMO", "M001-lead-request.md", "id: M001", 'id: "M001"')
        self.edit("TASK-DEMO", "M001-lead-request.md", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00+00:00")
        self.assertEqual(validate(self.root)[2], [])

    def test_date_only_clock_denial_is_not_a_utc_timestamp(self):
        self.edit("TASK-AUDIT", "M002-auditor-review.md", "2026-01-02T00:01:00Z", "2026-01-02 (clock denied)")
        self.assertIn("created_at must be UTC ISO-8601", "\n".join(validate(self.root)[2]))

    def test_pass_does_not_cover_unknown_artifact(self):
        self.edit("TASK-AUDIT", "M002-auditor-review.md", "version_ref: candidate-a", "version_ref: unknown")
        self.assertIn("PASS needs a known object_ref and version_ref", "\n".join(validate(self.root)[2]))

    def test_duplicate_message_id_within_task_is_rejected(self):
        directory = self.root / "TASK-DEMO" / "messages"
        shutil.copyfile(directory / "M001-lead-request.md", directory / "duplicate.md")
        self.assertIn("duplicate message ID within task", "\n".join(validate(self.root)[2]))


if __name__ == "__main__":
    unittest.main()
