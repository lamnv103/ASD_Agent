"""Answer-layer evaluation tools: verifier fault set, layered scoring, replay-mode selection. No provider calls."""
import json
import sys
import unittest

from rag.retriever import ROOT

sys.path.insert(0, str(ROOT / "scripts/evaluation"))
import measure_verifier as mv  # noqa: E402
import verify_answer_layer as va  # noqa: E402
import check_trial as ct  # noqa: E402
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


class AddendumTests(unittest.TestCase):
    """answer_verifier_faults_v1_addendum: paired cases, reported separately from v1 (never pooled)."""

    def test_pairs_have_a_clean_and_a_faulty_case_and_resolve(self):
        path = ROOT / "evaluation/answer_verifier_faults_v1_addendum/cases.jsonl"
        cases = mv.load_jsonl(path)
        self.assertFalse({c["case_id"] for c in cases} & {c["case_id"] for c in CASES})
        pairs = {}
        for c in cases:
            pairs.setdefault(c["pair"], set()).add(c["expected"])
        for pair, kinds in pairs.items():
            self.assertEqual(kinds, {"pass", "fail"}, pair)
        cfg, corpus, gate = load_config(), load_trusted_corpus(), load_pharm_gate()
        for c in cases:
            trace = json.loads((ROOT / c["trace"]).read_text(encoding="utf-8"))
            catalog, sources = build_catalog(trace, cfg, corpus)
            scope = gate.scope(trace["question"])
            claim = dict(claim_id="c1", role="chi_tiet", **c["claim"])
            self.assertEqual(check_claims_k1([claim], catalog, sources, {"n1"}, cfg, lambda t: gate.check(t, scope))["c1"], [],
                             c["case_id"])


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
        core, all_ = s["faults"]["core"], s["faults"]["all"]
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


class PipelineGroupTests(unittest.TestCase):
    def test_pipeline_group_rows_compare_with_the_full_group(self):
        cases = [_case("F1", "fail"), _case("F2", "fail")]
        records = [_rec("F1", dict(support="supported", flags=[]), []), _rec("F2", dict(support="supported", flags=[]), [])]
        full = [dict(group_id="G", records=[dict(case_id="F1", verifier_outcome="fail"), dict(case_id="F2", verifier_outcome="pass")])]
        pipe = [dict(group_id="G", records=[dict(case_id="F1", verifier_outcome="pass"), dict(case_id="F2", verifier_outcome=None)])]
        g = mv.score(cases, records, full, pipe)["pipeline_groups"]
        self.assertEqual(g["compared"], 1)  # F2 was removed before the verifier (not sent)
        self.assertEqual([(x["case_id"], x["verifier_full_group"], x["verifier_pipeline_group"]) for x in g["changed"]],
                         [("F1", "fail", "pass")])


class ContentReasonTests(unittest.TestCase):
    def test_mechanical_rejections_are_not_counted_as_the_right_reason(self):
        v = dict(support="supported", flags=[])
        cases = [_case("F1", "fail", flags=["condition_dropped"]), _case("F2", "fail", flags=["condition_dropped"])]
        records = [_rec("F1", v, ["check:population_scope:dropped"]),               # the right content reason via the table
                   _rec("F2", v, ["check_source_not_verbatim:population_scope"])]  # rejected only for broken wording
        row = mv.score(cases, records)["faults"]["core"]
        self.assertEqual(row["caught_verifier"], ["F1", "F2"])
        self.assertEqual(row["right_reason_verifier"], ["F1"])
        self.assertEqual(row["caught_verifier_mechanical_only"], ["F2"])


class VerifierErrorTests(unittest.TestCase):
    def test_invalid_verifier_output_is_a_mechanical_rejection(self):
        rec = dict(case_id="P1", k1_reasons=[], verdict=None, reasons=["verifier_output_invalid:gap verdict"],
                   verifier_error=True, outcome="fail", call=None)
        self.assertEqual(mv.layers(rec), (False, True, True))
        s = mv.score([_case("P1", "pass")], [rec])
        self.assertEqual(s["clean"]["false_reject_verifier_mechanical"], ["P1"])


class StabilityTests(unittest.TestCase):
    def test_repeated_measurements_flag_flipping_cases(self):
        v = dict(support="supported", flags=[])
        res = lambda outs: dict(cases_file=mv.DEFAULT_CASES, records=[  # noqa: E731
            _rec(cid, v, [] if o == "pass" else ["support_partially_supported"]) for cid, o in outs])
        rows = mv.stability([res([("P01", "pass"), ("F01", "pass")]), res([("P01", "fail"), ("F01", "pass")])])
        self.assertEqual({r["case_id"]: (r["verifier"], r["stable"]) for r in rows},
                         {"P01": (["pass", "fail"], False), "F01": (["pass", "pass"], True)})


class TrialCriteriaTests(unittest.TestCase):
    """check_trial.py judges a pre-registered trial; mechanical rejections never count as catching the fault."""

    def judge(self, single, groups=(), tok=300):
        crit = json.loads((ROOT / "evaluation/trials/verifier_v0.7_small/criteria.json").read_text(encoding="utf-8"))
        call = dict(cache_hit=False, usage=dict(completion_tokens=tok))
        res = dict(contract_version=crit["contract_version"],
                   records=[dict(case_id=c, outcome="fail" if r else "pass", reasons=r, call=call) for c, r in single],
                   groups=[dict(group_id=g, call=call, records=[dict(case_id=c, verifier_reasons=r,
                                verifier_outcome="fail" if r else "pass") for c, r in recs]) for g, recs in groups])
        crit["runs"] = crit["runs"][:1]
        orig = ct.load
        ct.load = lambda run: res
        try:
            return ct.judge(crit)[0]
        finally:
            ct.load = orig

    def test_rules(self):
        good = [("F01", ["check:conclusion_topic:changed"]), ("A01", ["support_partially_supported", "check:certainty:stronger"]),
                ("P03", []), ("A02", []), ("A04", []), ("A06", [])]
        grp = [("G1", [("P03", []), ("F01", ["check:certainty:stronger"])]), ("GA1", [("A02", []), ("A01", ["check:conclusion_topic:changed"])]),
               ("G8", [("P03", []), ("P08", []), ("F10", [])])]
        out = self.judge(good, grp)
        self.assertTrue(all(r["ok"] for r in out.values()), out)
        # F01 rejected only by v0.5 support or broken output: not the table reason -> R1 fails (and R4 for the error)
        out = self.judge([("F01", ["support_partially_supported"]), ("A01", ["verifier_output_invalid:checks"])] + good[2:], grp)
        self.assertFalse(out["R1_focal_single"]["ok"])
        self.assertFalse(out["R4_format"]["ok"])
        # a clean case rejected for any reason, inside a group, fails R3; a long call fails R5
        out = self.judge(good, grp[:2] + [("G8", [("P03", []), ("P08", ["support_partially_supported"])])], tok=2049)
        self.assertEqual(out["R3_clean"]["detail"], [("G8", "P08", ["support_partially_supported"])])
        self.assertFalse(out["R5_length"]["ok"])


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
