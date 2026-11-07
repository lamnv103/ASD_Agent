"""Answer-layer evaluation tools: verifier fault set, measurement scoring, replay-mode selection. No provider calls."""
import json
import sys
import unittest

from rag.retriever import ROOT

sys.path.insert(0, str(ROOT / "scripts/evaluation"))
import measure_verifier as mv  # noqa: E402
import verify_answer_layer as va  # noqa: E402
from rag.answer_layer import build_catalog, check_claims_k1  # noqa: E402
from rag.answer_policy import load_config  # noqa: E402
from rag.answer_sources import load_trusted_corpus  # noqa: E402

CASES = mv.load_cases(ROOT / mv.DEFAULT_CASES)


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

    def test_every_case_resolves_against_the_released_corpus_and_passes_k1(self):
        cfg, corpus = load_config(), load_trusted_corpus()
        for c in CASES:
            trace = json.loads((ROOT / c["trace"]).read_text(encoding="utf-8"))
            catalog, sources = build_catalog(trace, cfg, corpus)
            needs = {n["claim_id"] for n in trace["assessment_after_selection"]["claims"]}
            claim = dict(claim_id="c1", role="chi_tiet", **c["claim"])
            self.assertEqual(check_claims_k1([claim], catalog, sources, needs, cfg)["c1"], [], c["case_id"])


class ScoringTests(unittest.TestCase):
    def test_score_separates_clean_faults_contested_and_later_features(self):
        cases = [dict(case_id="P", expected="pass", measurable_from="v0.2", expected_flags_any=[], expected_support_any=[]),
                 dict(case_id="F1", expected="fail", measurable_from="v0.2", expected_flags_any=["negation_flipped"], expected_support_any=[]),
                 dict(case_id="F2", expected="fail", measurable_from="v0.2", expected_flags_any=["added_content"], expected_support_any=[]),
                 dict(case_id="F3", expected="fail", measurable_from="C", expected_flags_any=[], expected_support_any=[]),
                 dict(case_id="X", expected="contested", measurable_from="v0.2", expected_flags_any=[], expected_support_any=[])]
        v = lambda support, flags=(): dict(support=support, flags=list(flags))  # noqa: E731
        records = [dict(case_id="P", outcome="fail", verdict=v("partially_supported"), k1_reasons=[]),
                   dict(case_id="F1", outcome="fail", verdict=v("contradicted", ["negation_flipped"]), k1_reasons=[]),
                   dict(case_id="F2", outcome="pass", verdict=v("supported"), k1_reasons=[]),
                   dict(case_id="F3", outcome="pass", verdict=v("supported"), k1_reasons=[]),
                   dict(case_id="X", outcome="fail", verdict=v("partially_supported"), k1_reasons=[])]
        s = mv.score(cases, records, "answer_contract_v0.2")
        self.assertEqual((s["clean"], s["false_reject"]), (1, ["P"]))
        self.assertEqual((s["faults_scored"], s["caught"], s["missed"], s["right_reason"]), (2, ["F1"], ["F2"], ["F1"]))
        self.assertEqual([x["case_id"] for x in s["not_yet_measurable"]], ["F3"])
        self.assertEqual(s["contested"], [dict(case_id="X", outcome="fail")])
        later = mv.score(cases, records, "answer_contract_v0.3")
        self.assertEqual((later["faults_scored"], later["missed"]), (3, ["F2", "F3"]))


class ReplayModeTests(unittest.TestCase):
    def test_v02_bundle_replays_with_its_own_commit(self):
        manifest = json.loads((ROOT / "reports/answer_eval_20261107/manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(va.replay_mode(manifest), "legacy")  # answer-layer code moved on after e0f3cc1
        old = va.fingerprint_at(manifest["code_commit_at_run"])
        self.assertEqual(set(old), set(va.CODE_FILES))
        self.assertNotEqual(old["rag/answer_layer.py"], va.fingerprint(ROOT)["rag/answer_layer.py"])

    def test_current_mode_requires_same_code_and_pins(self):
        manifest = dict(code_commit_at_run="HEAD", code_fingerprint=va.fingerprint(ROOT),
                        pinned_files=va.fingerprint(ROOT, va.PINNED_FILES))
        self.assertEqual(va.replay_mode(manifest), "current")
        manifest["pinned_files"] = dict(manifest["pinned_files"], **{"deployments/answer_layer.json": "0" * 64})
        self.assertEqual(va.replay_mode(manifest), "legacy")


if __name__ == "__main__":
    unittest.main()
