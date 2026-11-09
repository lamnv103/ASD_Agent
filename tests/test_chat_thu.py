"""Internal test chat (scripts/dev/chat_thu.py): key-file handling and display helpers. No provider calls."""
import sys
import tempfile
import unittest
from pathlib import Path

from rag.retriever import ROOT

sys.path.insert(0, str(ROOT / "scripts/dev"))
import chat_thu  # noqa: E402


class ChatThuTests(unittest.TestCase):
    def test_key_slot_detection_never_needs_the_value_printed(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "k.env"
            p.write_text("COHERE_API_KEY=\n", encoding="utf-8")
            self.assertFalse(chat_thu.has_value(p, "COHERE_API_KEY"))  # empty slot -> hidden prompt
            p.write_text("COHERE_API_KEY=abc\n", encoding="utf-8")
            self.assertTrue(chat_thu.has_value(p, "COHERE_API_KEY"))
            self.assertFalse(chat_thu.has_value(Path(d) / "missing.env", "COHERE_API_KEY"))

    def test_banner_and_removed_claims(self):
        self.assertIn("NỘI BỘ", chat_thu.BANNER)
        self.assertIn("GIẢ ĐỊNH", chat_thu.BANNER)
        out = chat_thu.removed_text(dict(claims_removed=[dict(round="repair", disposition="failed_verification",
                                                              text="x", reasons=["support_not_supported"])]))
        self.assertIn("support_not_supported", out)
        self.assertIn("không có", chat_thu.removed_text(dict(claims_removed=[])))

    def test_sessions_are_git_ignored(self):
        self.assertIn("reports/chat_thu/", (ROOT / ".gitignore").read_text(encoding="utf-8"))

    def test_prepared_questions_need_no_cohere_key(self):
        samples = chat_thu.prepared()
        self.assertEqual(sorted(samples), ["H03", "H04", "H05", "S05", "S07", "S08"])
        self.assertTrue(all(t["question"].strip() for t in samples.values()))
