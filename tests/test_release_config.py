"""deployments/database.env: local connection may differ, release settings may not."""
import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "evaluation"))
import audit_output  # noqa: E402

GOOD = ("RAG_DATABASE_URL=postgresql://postgres:{pw}@{host}:{port}/{db}\n"
        "RAG_COLLECTION=asd_fulltext_33_20261030_26eb017efca5\n"
        "RAG_EMBEDDING_SPACE=cohere4_whole_1536_e83c596b9070\n"
        "RAG_EMBEDDING_PROVIDER=cohere\nRAG_EMBEDDING_MODEL={model}\n"
        "RAG_EMBEDDING_DIMENSIONS=1536\nRAG_WHOLE_DOCUMENT=true\n")


class LocalConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "deployments").mkdir()
        release = json.loads((ROOT / "deployments/database.release.json").read_text(encoding="utf-8"))
        self.original = GOOD.format(pw="original", host="127.0.0.1", port=5433, db="asd_rag", model="embed-v4.0")
        self.pin = hashlib.sha256(self.original.encode()).hexdigest()
        release["historical_pin_sha256"] = self.pin
        (self.tmp / "deployments/database.release.json").write_text(json.dumps(release), encoding="utf-8")
        self._root, self._release = audit_output.ROOT, audit_output.RELEASE_DB
        audit_output.ROOT, audit_output.RELEASE_DB = self.tmp, self.tmp / "deployments/database.release.json"

    def tearDown(self):
        audit_output.ROOT, audit_output.RELEASE_DB = self._root, self._release
        shutil.rmtree(self.tmp)

    def check(self, text):
        (self.tmp / "deployments/database.env").write_text(text, encoding="utf-8", newline="\n")
        return audit_output.protected_ok("deployments/database.env", self.pin)

    def test_exact_historical_file_passes(self):
        self.assertEqual(self.check(self.original), (True, "exact historical pin"))

    def test_other_password_host_and_port_pass(self):
        ok, why = self.check(GOOD.format(pw="another-secret", host="localhost", port=5435, db="asd_rag", model="embed-v4.0"))
        self.assertTrue(ok, why)
        self.assertIn("local connection differs", why)

    def test_release_settings_and_database_name_cannot_change(self):
        for text in [GOOD.format(pw="x", host="h", port=1, db="other_db", model="embed-v4.0"),
                     GOOD.format(pw="x", host="h", port=1, db="asd_rag", model="embed-v5.0"),
                     GOOD.format(pw="x", host="h", port=1, db="asd_rag", model="embed-v4.0").replace(
                         "asd_fulltext_33_20261030_26eb017efca5", "another_collection")]:
            ok, _ = self.check(text)
            self.assertFalse(ok, text)

    def test_missing_file_fails(self):
        ok, _ = audit_output.protected_ok("deployments/database.env", self.pin)
        self.assertFalse(ok)

    def test_other_pinned_files_still_need_exact_hash(self):
        (self.tmp / "x.json").write_text("{}", encoding="utf-8")
        self.assertFalse(audit_output.protected_ok("x.json", "0" * 64)[0])
        self.assertTrue(audit_output.protected_ok("x.json", hashlib.sha256(b"{}").hexdigest())[0])


if __name__ == "__main__":
    unittest.main()
