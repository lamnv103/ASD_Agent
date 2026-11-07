"""Run safety (no lost paid calls) and trial judging. Mock clients only; no provider calls."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from rag.retriever import ROOT, atomic_json

sys.path.insert(0, str(ROOT / "scripts/evaluation"))
import check_trial as ct  # noqa: E402
import measure_verifier as mv  # noqa: E402
import run_trial as rtr  # noqa: E402

TMP = "reports/_test_trial_tools_tmp"


class FakeClient:
    def __init__(self, fail=None):
        self.calls, self.fail = 0, fail

    def complete(self, msgs):
        self.calls += 1
        if self.fail:
            raise self.fail
        return dict(content="{}", cache_hit=False, request_id="r1", usage=dict(completion_tokens=12))


class TmpReports(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(ROOT / TMP, ignore_errors=True)

    def tearDown(self):
        shutil.rmtree(ROOT / TMP, ignore_errors=True)


class OutPathTests(unittest.TestCase):
    def test_bad_paths_are_refused_before_any_call(self):
        for bad in ("reports/x\r", " reports/x", "reports/x ", "reports/a\tb", "../x", "evaluation/x", "", "reports"):
            with self.assertRaises(mv.RunAbort, msg=repr(bad)):
                mv.validate_out(bad)
        self.assertEqual(mv.validate_out("reports/a/b"), (ROOT / "reports/a/b").resolve())


class LedgerTests(unittest.TestCase):
    def test_every_call_is_logged_before_it_is_made(self):
        with tempfile.TemporaryDirectory() as d:
            led = mv.Ledger(Path(d) / "calls.jsonl")
            ok = mv.LedgerClient(FakeClient(), led)
            ok.complete([])
            lost = mv.LedgerClient(FakeClient(OSError("cache write failed after the response")), led)
            lost.n = 1
            with self.assertRaises(OSError):
                lost.complete([])
            s = led.summary()
            self.assertEqual((s["attempted"], s["completed"], s["provider_calls"], s["errors"], s["completion_tokens"]),
                             (2, 1, 1, ["OSError"], 12))

    def test_no_call_when_the_ledger_cannot_be_written(self):
        fake = FakeClient()
        client = mv.LedgerClient(fake, mv.Ledger(Path(tempfile.gettempdir()) / "no_such_dir_x9" / "calls.jsonl"))
        with self.assertRaises(OSError):
            client.complete([])
        self.assertEqual(fake.calls, 0)


class PreflightTests(TmpReports):
    def test_preflight_proves_cache_and_ledger_writable(self):
        out = ROOT / TMP / "m1"
        mv.preflight(out, atomic_json)
        self.assertEqual([p.name for p in (out / "cache").iterdir()], [])  # probe removed
        self.assertEqual(mv.Ledger(out / "calls.jsonl").summary()["attempted"], 0)

    def test_interrupted_folder_is_never_reused(self):
        out = ROOT / TMP / "m2"
        out.mkdir(parents=True)
        (out / "results.partial.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(mv.RunAbort):
            mv.preflight(out, atomic_json)

    def test_main_refuses_a_bad_out_before_building_anything(self):
        with mock.patch.object(mv, "Runtime", side_effect=AssertionError("must not start")), \
                mock.patch.object(sys, "argv", ["mv", "--out", "reports/x\r"]):
            with self.assertRaises(SystemExit) as cm:
                mv.main()
        self.assertIn("preflight", str(cm.exception.code))

    def test_failure_mid_run_stops_and_keeps_partial_state(self):
        fake = FakeClient(OSError("disk full"))

        class FakeRuntime:
            atomic_json = staticmethod(atomic_json)
            counter = None

            def client_cls(self, counter, key_file=None, cache_dir=None):
                return fake

            def check_case(self, case, client):
                client.complete([])

        with mock.patch.object(mv, "Runtime", FakeRuntime), \
                mock.patch.object(sys, "argv", ["mv", "--out", TMP + "/m3", "--only", "P03,P08", "--no-groups"]):
            with self.assertRaises(OSError):
                mv.main()
        self.assertEqual(fake.calls, 1)  # stopped at the first failure; P08 never sent
        partial = json.loads((ROOT / TMP / "m3/results.partial.json").read_text(encoding="utf-8"))
        self.assertEqual((partial["ledger"]["attempted"], partial["ledger"]["completed"]), (1, 0))
        self.assertIn("disk full", partial["error"])
        self.assertFalse((ROOT / TMP / "m3/results.json").exists())


class RunTrialTests(TmpReports):
    def crit(self, **kw):
        runs = [dict(out=f"{TMP}/r{i}", cases="evaluation/answer_verifier_faults_v1/cases.jsonl", only="P03") for i in (1, 2, 3)]
        return dict(dict(trial_id="t", status="registered", contract_version="answer_contract_vX", state_file=f"{TMP}/state.json",
                         runs=runs), **kw)

    def test_drafts_and_contract_mismatch_are_refused(self):
        with self.assertRaises(mv.RunAbort):
            rtr.plan(self.crit(status="draft"), contract="answer_contract_vX")
        with self.assertRaises(mv.RunAbort):
            rtr.plan(self.crit(), contract="answer_contract_vY")
        bad = self.crit()
        bad["runs"][2]["out"] += "\r"
        with self.assertRaises(mv.RunAbort):  # checked for every run before the first one starts
            rtr.plan(bad, contract="answer_contract_vX")

    def test_first_failure_stops_the_batch(self):
        seen = []

        def runner(argv, cwd):
            seen.append(argv)
            self.assertIsInstance(argv, list)  # argument list, no shell parsing
            return SimpleNamespace(returncode=1 if len(seen) == 2 else 0)

        self.assertEqual(rtr.execute(self.crit(), None, runner=runner, contract="answer_contract_vX"), 1)
        self.assertEqual(len(seen), 2)
        st = json.loads((ROOT / TMP / "state.json").read_text(encoding="utf-8"))
        self.assertEqual([r["status"] for r in st["runs"]], ["done", "failed", "pending"])


class JudgeTests(unittest.TestCase):
    CRIT = dict(contract_version="v", decision={}, runs=[dict(out="o", only="F02,P08", stage="trial")], rules=[
        dict(id="R1", type="rejected_for", reasons_any=["context_limit:E2"], reps={"single": 1},
             select=[dict(where="single", cases=["F02"])]),
        dict(id="R2", type="never_rejected", reps={"single": 1}, select=[dict(where="single", cases=["P08"])])])

    def judge(self, records):
        res = dict(contract_version="v", records=[dict(case_id=c, outcome="fail" if r else "pass", reasons=r, call=None)
                                                   for c, r in records])
        with mock.patch.object(ct, "load", lambda run: res):
            return ct.judge(json.loads(json.dumps(self.CRIT)))

    def test_mechanical_reasons_are_not_a_catch(self):
        out, rep, problems = self.judge([("F02", ["context_span_not_verbatim", "support_contradicted"]), ("P08", [])])
        self.assertFalse(out["R1"]["ok"])
        self.assertTrue(out["R2"]["ok"])
        self.assertEqual(rep["mechanical"], [("trial", "single", "F02", "context_span_not_verbatim")])
        out, _, _ = self.judge([("F02", ["context_limit:E2"]), ("P08", [])])
        self.assertTrue(all(r["ok"] for r in out.values()))

    def test_missing_case_or_repetition_blocks_judging(self):
        _, _, problems = self.judge([("F02", ["context_limit:E2"])])
        self.assertEqual(problems, ["o: single/P08"])


class CriteriaFileTests(unittest.TestCase):
    def test_c_draft_is_consistent_and_not_runnable(self):
        crit = json.loads((ROOT / "evaluation/trials/verifier_c_small/criteria.json").read_text(encoding="utf-8"))
        with self.assertRaises(mv.RunAbort):  # a draft can never start provider calls
            rtr.plan(crit, contract=crit["contract_version"], stage="trial")
        cases = {}
        for f in {r["cases"] for r in crit["runs"]}:
            cases.update({c["case_id"]: c for c in mv.load_jsonl(ROOT / f)})
        singles = {c for r in crit["runs"] if r.get("stage") == "trial" and "only" in r for c in r["only"].split(",")}
        groups = {g["group_id"]: g["case_ids"] for r in crit["runs"] if "groups" in r for g in mv.load_jsonl(ROOT / r["groups"])}
        for rule in crit["rules"]:
            for s in rule.get("select", []):
                where = s["where"].split("/")[0]
                for c in s["cases"]:
                    self.assertIn(c, singles if where == "single" else groups[where], (rule["id"], s["where"], c))
                    want = "pass" if rule["type"] == "never_rejected" else "fail"
                    self.assertEqual(cases[c]["expected"], want, (rule["id"], c))  # rules never contradict labels
        calls = {st: sum(len(r["only"].split(",")) if "only" in r else len(mv.load_jsonl(ROOT / r["groups"])) + len(r.get("pipeline", {}))
                         for r in crit["runs"] if r["stage"] == st) for st in ("baseline", "trial")}
        self.assertEqual(calls, crit["calls_planned"])


class CaseSetTests(unittest.TestCase):
    def test_c_cases_are_clean_for_k1_and_paired(self):
        from rag.answer_layer import build_catalog, check_claims_k1
        from rag.answer_pharm import load_pharm_gate
        from rag.answer_policy import load_config
        from rag.answer_sources import load_trusted_corpus
        cfg, corpus, gate = load_config(), load_trusted_corpus(), load_pharm_gate()
        cases = mv.load_jsonl(ROOT / "evaluation/answer_verifier_faults_c/cases.jsonl")
        v1 = {c["case_id"] for c in mv.load_jsonl(ROOT / mv.DEFAULT_CASES)}
        self.assertFalse({c["case_id"] for c in cases} & v1)
        for c in cases:
            trace = json.loads((ROOT / c["trace"]).read_text(encoding="utf-8"))
            catalog, sources = build_catalog(trace, cfg, corpus)
            scope = gate.scope(trace["question"])
            claim = dict(claim_id="c1", role="chi_tiet", **c["claim"])
            self.assertEqual(check_claims_k1([claim], catalog, sources, {"n1"}, cfg, lambda t: gate.check(t, scope))["c1"], [],
                             c["case_id"])
            if c["fault_type"] == "support_only_in_uncited":  # the support really sits in an uncited passage
                self.assertGreater(len(catalog), len(c["claim"]["evidence_ids"]))
        self.assertEqual({c["expected"] for c in cases if c.get("pair") == "KC1"}, {"pass", "fail"})


if __name__ == "__main__":
    unittest.main()
