"""Environment check (lockfile comparison) and database-failure classification used by the test runner."""
import sys
import tempfile
import unittest
from pathlib import Path

from rag.retriever import ROOT

sys.path.insert(0, str(ROOT / "scripts/dev"))
import check_env  # noqa: E402
import env_diagnose  # noqa: E402


class CheckEnvTests(unittest.TestCase):
    def test_names_are_normalized(self):
        for a, b in (("huggingface_hub", "huggingface-hub"), ("PyYAML", "pyyaml"), ("zope.interface", "zope-interface"),
                     ("typing__extensions", "typing-extensions")):
            self.assertEqual(check_env.norm(a), check_env.norm(b))

    def test_compare_reports_missing_mismatch_extra_but_not_spelling(self):
        lock = {"huggingface-hub": "2.4.0", "psycopg2-binary": "2.9.13", "jinja2": "3.1.6"}
        inst = {"huggingface-hub": "2.4.0", "jinja2": "3.1.5", "langchain-core": "1.7.6", "pip": "25.0"}
        missing, mismatch, extra = check_env.compare(lock, inst)
        self.assertEqual(missing, ["psycopg2-binary"])
        self.assertEqual(mismatch, [("jinja2", "3.1.6", "3.1.5")])
        self.assertEqual(extra, ["langchain-core"])

    def test_lockfile_parsing(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "lock.txt"
            p.write_text("# comment\nHuggingface_Hub==2.4.0  # pinned\n\nJinja2==3.1.6\n", encoding="utf-8")
            self.assertEqual(check_env.read_lock(p), {"huggingface-hub": "2.4.0", "jinja2": "3.1.6"})
            p.write_text("requests>=2\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                check_env.read_lock(p)

    def test_current_lockfile_is_parseable(self):
        self.assertEqual(len(check_env.read_lock()), 38)


class DiagnoseTests(unittest.TestCase):
    def test_operational_error_classification(self):
        cases = {
            'connection to server at "127.0.0.1", port 5999 failed: Connection refused': "database_unreachable",
            "could not translate host name \"nohost\" to address": "database_unreachable",
            "timeout expired": "database_unreachable",
            'connection to server failed: FATAL:  password authentication failed for user "x"': "database_auth",
            'FATAL:  database "nope" does not exist': "database_missing",
            "FATAL:  sorry, too many clients already": "database_error",
        }
        for message, code in cases.items():
            self.assertEqual(env_diagnose.classify_operational(message), code, message)

    def test_missing_database_env_is_config_error(self):
        with tempfile.TemporaryDirectory() as d:
            empty = Path(d) / "empty.env"
            empty.write_text("# nothing\n", encoding="utf-8")
            self.assertEqual(env_diagnose.diagnose(empty)["code"], "database_config")
            self.assertEqual(env_diagnose.diagnose(Path(d) / "absent.env")["code"], "database_config")

    def test_every_code_has_a_hint(self):
        for code in ("ok", "dependency_missing", "database_config", "database_unreachable", "database_auth",
                     "database_missing", "database_error", "database_integrity", "config_invalid"):
            self.assertTrue(env_diagnose.HINTS[code])


if __name__ == "__main__":
    unittest.main()
