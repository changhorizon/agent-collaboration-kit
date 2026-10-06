import unittest
from pathlib import Path


class CandidateTest(unittest.TestCase):
    def test_candidate_is_ready(self):
        path = Path(__file__).with_name("candidate.txt")
        self.assertEqual(path.read_text(encoding="utf-8").strip(), "ready")


if __name__ == "__main__":
    unittest.main()
