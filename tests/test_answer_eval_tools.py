"""Answer-layer evaluation tools: verifier fault set, layered scoring, replay-mode selection. No provider calls."""
import json
import sys
import unittest

from rag.retriever import ROOT

sys.path.insert(0, str(ROOT / "scripts/evaluation"))
import measure_verifier as mv  # noqa: E402
import verify_answer_layer as va  # noqa: E402
from rag.answer_layer import build_catalog, check_claims_k1  # noqa: E402
from rag.answer_pharm import load_pharm_gate  # noqa: E402
from rag.answer_policy import load_config  # noqa: E402
from rag.answer_sources import load_trusted_corpus  # noqa: E402

CASES = mv.load_jsonl(ROOT / mv.DEFAULT_CASES)
GROUPS = mv.load_jsonl(ROOT / mv.DEFAULT_GROUPS)


class FaultSetTests(unittest.TestCase):
    def test_case_file_is_well_formed(self):
        ids = [c["case_id"] for c in CASES]
        self.assertEqual(len(ids), len(set(ids)))
        for c in CASES:
            self.assertIn(c["expected"], ("pass", "fail", "contested"), c["case_id"])
            self.assertEqual(c["label"] == "contested", c["expected"] == "contested", c["case_id"])
            self.assertTrue(c["measurable_from"], c["case_id"])
            if c["expected"] == "fail":
                self.assertTrue(c["fault_type"] != "none", c["case_id"])
        faults = [c for c in CASES if c["expected"] == "fail"]
        self.assertEqual((len(faults), sum(c["measurable_from"] == "v0.2" for c in faults)), (18, 16))  # fixed denominators

    def test_groups_use_one_trace_and_known_cases(self):
        by_id = {c["case_id"]: c for c in CASES}
        for g in GROUPS:
            traces = {by_id[c]["trace"] for c in g["case_ids"]}
            self.assertEqual(len(traces), 1, g["group_id"])
            self.assertEqual(by_id[g["case_ids"][0]]["question_id"], g["question_id"])

    def test_cases_resolve_and_deterministic_blocks_are_exactly_known(self):
        cfg, corpus, gate = load_config(), load_trusted_corpus(), load_pharm_gate()
        blocked, terms = [], []
        for c in CASES:
            trace = json.loads((ROOT / c["trace"]).read_text(encoding="utf-8"))
            catalog, sources = build_catalog(trace, cfg, corpus)
            needs = {n["claim_id"] for n in trace["assessment_after_selection"]["claims"]}
            claim = dict(claim_id="c1", role="chi_tiet", **c["claim"])
            scope = gate.scope(trace["question"])
            reasons = check_claims_k1([claim], catalog, sources, needs, cfg, lambda t: gate.check(t, scope))["c1"]
            self.assertTrue(all(r.startswith(("pharm_unrequested:", "known_term_error:")) for r in reasons), (c["case_id"], reasons))
            if any(r.startswith("pharm_unrequested:") for r in reasons):
                blocked.append(c["case_id"])
            if any(r.startswith("known_term_error:") for r in reasons):
                terms.append(c["case_id"])
        self.assertEqual(blocked, ["F11"])  # H03 medication content (P01, P10, F07, F08, F18) is requested
        self.assertEqual(terms, ["F04", "F05"])  # the two observed mistranslations; corrected P04/P05 pass


def _case(cid, expected, mf="v0.2", flags=()):
    return dict(case_id=cid, expected=expected, measurable_from=mf, expected_flags_any=list(flags), expected_support_any=[])


def _rec(cid, verdict, reasons, gate=(), k1=()):
    r = dict(case_id=cid, k1_reasons=list(k1), verdict=verdict, reasons=list(gate) + list(reasons), call=None)
    if gate:
        r.update(gate_reasons=list(gate), verifier_reasons=list(reasons))
    r["outcome"] = "fail" if r["reasons"] else "pass"
    return r


class ScoringTests(unittest.TestCase):
    def test_layers_and_fixed_denominators(self):
        v = lambda support, flags=(): dict(support=support, flags=list(flags))  # noqa: E731
        cases = [_case("P", "pass"), _case("F1", "fail", flags=["negation_flipped"]), _case("F2", "fail"),
                 _case("F3", "fail", mf="C"), _case("X", "contested")]
        records = [_rec("P", v("supported"), []),
                   _rec("F1", v("contradicted", ["negation_flipped"]), ["support_contradicted"]),
                   _rec("F2", v("supported"), [], gate=["pharm_unrequested:drug_name:melatonin"]),  # gate only
                   _rec("F3", v("supported"), []),
                   _rec("X", v("partially_supported"), ["support_partially_supported"])]
        s = mv.score(cases, records)
        self.assertEqual(s["clean"]["false_reject_system"], [])
        core, all_ = s["faults"]["core16"], s["faults"]["all18"]
        self.assertEqual((core["n"], all_["n"]), (2, 3))
        self.assertEqual(core["caught_system"], ["F1", "F2"])
        self.assertEqual(core["blocked_deterministic"], ["F2"])
        self.assertEqual(core["caught_verifier"], ["F1"])       # the gate does not count as a verifier improvement
        self.assertEqual(core["missed_verifier"], ["F2"])
        self.assertEqual(all_["missed_system"], ["F3"])
        self.assertEqual(s["contested"], [dict(case_id="X", outcome="fail")])

    def test_single_vs_group_disagreement(self):
        cases = [_case("F1", "fail")]
        records = [_rec("F1", dict(support="contradicted", flags=[]), ["support_contradicted"])]
        groups = [dict(group_id="G", records=[dict(case_id="F1", verifier_outcome="pass")])]
        g = mv.score(cases, records, groups)["groups"]
        self.assertEqual([(x["case_id"], x["verifier_single"], x["verifier_group"]) for x in g["disagree"]],
                         [("F1", "fail", "pass")])


class ReplayModeTests(unittest.TestCase):
    def test_v02_bundle_replays_with_its_own_commit(self):
        manifest = json.loads((ROOT / "reports/answer_eval_20261107/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(va.replay_mode(manifest), "legacy")  # answer-layer code moved on after e0f3cc1
        old = va.fingerprint_at(manifest["code_commit_at_run"])
        self.assertEqual(set(old), set(va.CODE_FILES))
        self.assertIsNone(old["rag/answer_pharm.py"])  # files added later are recorded as absent
        self.assertNotEqual(old["rag/answer_layer.py"], va.fingerprint(ROOT)["rag/answer_layer.py"])

    def test_current_mode_requires_same_code_and_pins(self):
        manifest = dict(code_commit_at_run="HEAD", code_fingerprint=va.fingerprint(ROOT),
                        pinned_files=va.fingerprint(ROOT, va.PINNED_FILES))
        self.assertEqual(va.replay_mode(manifest), "current")
        manifest["pinned_files"] = dict(manifest["pinned_files"], **{"deployments/answer_layer.json": "0" * 64})
        self.assertEqual(va.replay_mode(manifest), "legacy")


if __name__ == "__main__":
    unittest.main()
