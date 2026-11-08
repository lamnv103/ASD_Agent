"""Repair-term guidance trial (direction 1). Offline only: recorded bundle replays and mock reviews; no provider calls."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from rag.answer_policy import load_config
from rag.answer_repair_terms import annotate_problems, load_term_guidance
from rag.retriever import ROOT

sys.path.insert(0, str(ROOT / "scripts/evaluation"))
import measure_repair as mr  # noqa: E402
import measure_verifier as mv  # noqa: E402
import run_trial as rtr  # noqa: E402
import verify_answer_layer as va  # noqa: E402

CFG = load_config()
G = load_term_guidance(known_terms=CFG["known_term_errors"]["terms"])
BUNDLE = "reports/answer_eval_20261107_v0.5"
UNITS = mr.load_units("evaluation/answer_repair_terms_v1/units.jsonl")
CRIT = json.loads((ROOT / "evaluation/trials/repair_terms_small/criteria.json").read_text(encoding="utf-8"))


class GuidanceTests(unittest.TestCase):
    def test_guidance_matches_known_terms(self):
        self.assertEqual(set(G["terms"]), set(CFG["known_term_errors"]["terms"]))
        self.assertEqual(G["terms"]["du lượn"]["use"], "đu đưa thụ động")

    def test_only_term_problems_are_annotated_and_codes_kept(self):
        probs = [dict(claim_id="c2", reasons=["known_term_error:nguyên tắc trung thực"], explanation=""),
                 dict(claim_id="c5", reasons=["support_partially_supported", "flag_condition_dropped"], explanation="x")]
        before = copy.deepcopy(probs)
        out = annotate_problems(probs, G)
        self.assertEqual(probs, before)  # input untouched
        self.assertEqual(out[0]["reasons"], ["known_term_error:nguyên tắc trung thực"])  # code kept for traceability
        self.assertEqual(out[0]["term_guidance"], [dict(wrong="nguyên tắc trung thực", source_term="fidelity principles",
                                                        use="nguyên tắc bảo đảm thực hiện đúng phương pháp")])
        self.assertEqual(out[1], probs[1])  # other reason codes are NOT reworded (no scope feedback mixed in)
        self.assertEqual(annotate_problems(probs[1:], G), probs[1:])


class OfflinePreconditionTests(unittest.TestCase):
    """The arms share the same first round; guidance changes nothing where there is no term error."""

    @classmethod
    def setUpClass(cls):
        cls.rt = mr.Runtime()

    def run_unit(self, unit, arm):
        live = self.rt.client_cls(self.rt.counter, key_supplier=va.no_key, cache_dir=ROOT / BUNDLE / "cache", offline=True)
        with va.NoNetwork():
            return self.rt.run(unit, arm, live)

    def test_run2_reproduced_except_s08_repair_in_arm_b(self):
        for q in ("S05", "S07", "H03", "S08"):
            exp = json.loads((ROOT / BUNDLE / f"{q}.result.json").read_text(encoding="utf-8"))
            for arm in ("A", "B"):
                res, sent = self.run_unit(dict(unit_id="t", question_id=q, bundle=BUNDLE), arm)
                if q == "S08" and arm == "B":
                    self.assertEqual(res["route"], "system_error")  # only the repair request differs (not in the bundle)
                    self.assertEqual([p["claim_id"] for p in sent if "term_guidance" in p], ["c2", "c3"])
                    continue
                self.assertTrue(all(res.get(k) == exp.get(k) for k in va.COMPARED), (q, arm))
                self.assertEqual(res["render"]["text"], exp["render"]["text"], (q, arm))
        h03 = json.loads((ROOT / BUNDLE / "H03.result.json").read_text(encoding="utf-8"))
        self.assertEqual(h03["repairs"], 0)  # a passing answer is not sent to repair in either arm

    def test_u2_shares_the_recorded_first_round_u3_does_not(self):
        res, _ = self.run_unit(UNITS["U2"], "A")  # first round replays; only its (new) repair request is unknown offline
        self.assertEqual(res["route"], "system_error")
        with self.assertRaises(mr.FirstRoundMismatch):  # U3 changes what is sent to the first verifier call
            self.run_unit(UNITS["U3"], "B")

    def test_held_out_variants(self):
        from rag.answer_layer import check_claims_k1, build_catalog
        from rag.answer_sources import load_trusted_corpus
        from rag.answer_pharm import load_pharm_gate
        gate = load_pharm_gate()
        for uid, expect in (("U2", {"c2", "c3"}), ("U3", set())):
            trace, _, raw = self.rt.unit_inputs(UNITS[uid])
            catalog, sources = build_catalog(trace, CFG, load_trusted_corpus())
            scope = gate.scope(trace["question"])
            claims = json.loads(raw)["claims"]
            k1 = check_claims_k1(claims, catalog, sources, {"n1"}, CFG, lambda t: gate.check(t, scope))
            self.assertEqual({c for c, r in k1.items() if any(x.startswith("known_term_error:") for x in r)}, expect, uid)
        _, _, raw = self.rt.unit_inputs(UNITS["U2"])
        self.assertIn("hiệu quả hơn ASI", raw)


def _fake(spec):
    """spec: {(unit, arm, rep): [(concepts, term_correct, faithful, wrong_content)]} -> displayed rows, key, review list."""
    rows, key, reviews, n = [], {}, [], 0
    for (unit, arm, rep), claims in spec.items():
        out = f"reports/repair_terms_small/{unit}_{arm}_rep{rep}"
        for i, (concepts, term, faithful, wrong) in enumerate(claims):
            n += 1
            rid, text = f"R{n:03d}", f"claim {n}"
            rows.append(dict(out=out, unit_id=unit, arm=arm, claim_id=f"c{i + 1}", text=text, cited=[]))
            key[rid] = dict(out=out, unit_id=unit, arm=arm, claim_id=f"c{i + 1}", text_sha256=mr._text_sha(text))
            reviews.append(dict(review_id=rid, concepts=list(concepts), term_correct=term, faithful=faithful,
                                contains_known_wrong_content=wrong, note=""))
    return rows, key, reviews


class JudgeTests(unittest.TestCase):
    GOOD = [(["K_ANSWER"], "na", "y", "n"), (["K_FIDELITY"], "y", "y", "n"), (["K_SWING"], "y", "y", "n")]

    def spec(self, override=None):
        spec = {}
        for unit in ("U1", "U2"):
            for rep in (1, 2, 3):
                spec[(unit, "A", rep)] = [(["K_ANSWER"], "na", "y", "n")]  # control keeps failing the terms
                spec[(unit, "B", rep)] = list(self.GOOD)
        spec.update(override or {})
        return spec

    def judge(self, override=None):
        rows, key, reviews = _fake(self.spec(override))
        return mr.judge(CRIT, reviews, key, rows)

    def test_all_pass_and_attribution(self):
        out, rep, problems = self.judge()
        self.assertEqual(problems, [])
        self.assertTrue(all(r["ok"] for r in out.values()), out)
        self.assertEqual(out["attribution"]["fixed_reps"], dict(A=0, B=3))
        self.assertIn("does not show a stable improvement", out["attribution"]["scope"])
        self.assertEqual(rep["reports/repair_terms_small/U2_B_rep1"]["u2_handling"], "comparison_removed_claim_kept")

    def test_dropping_the_claim_is_not_a_fix(self):
        out, rep, _ = self.judge({("U1", "B", 2): [(["K_ANSWER"], "na", "y", "n"), (["K_FIDELITY"], "y", "y", "n")]})
        self.assertFalse(out["R1_terms_fixed"]["ok"])
        out, rep, _ = self.judge({("U2", "B", 1): [(["K_ANSWER"], "na", "y", "n")]})
        self.assertTrue(out["R4_content_error_not_rescued"]["ok"])  # U2: dropping the whole claim is acceptable ...
        self.assertEqual(rep["reports/repair_terms_small/U2_B_rep1"]["u2_handling"], "claim_dropped")  # ... and reported apart

    def test_na_is_not_a_term_fix(self):
        out, _, _ = self.judge({("U1", "B", 1): [(["K_ANSWER"], "na", "y", "n"), (["K_FIDELITY"], "na", "y", "n"),
                                                 (["K_SWING"], "y", "y", "n")]})
        self.assertFalse(out["R1_terms_fixed"]["ok"])
        self.assertFalse(out["R3_no_new_error"]["ok"])

    def test_fixed_word_on_wrong_content_is_a_failure(self):
        out, rep, _ = self.judge({("U2", "B", 1): [(["K_SWING"], "y", "n", "y")]})
        self.assertFalse(out["R4_content_error_not_rescued"]["ok"])
        self.assertFalse(out["R5_U2_concept_clean"]["ok"])
        self.assertEqual(rep["reports/repair_terms_small/U2_B_rep1"]["u2_handling"], "wrong_content_shown")

    def test_no_benefit_when_control_also_fixes(self):
        out, _, _ = self.judge({("U1", "A", r): list(self.GOOD) for r in (1, 2, 3)})
        self.assertFalse(out["attribution"]["ok"])

    def test_every_displayed_claim_needs_exactly_one_valid_review(self):
        rows, key, reviews = _fake(self.spec({("U2", "B", 1): [(["K_SWING"], "y", "n", "y")]}))
        bad_rid = next(r for r, k in key.items() if k["out"].endswith("U2_B_rep1"))
        # the wrong-content claim is missing from BOTH the key and the review: must not pass silently
        k2 = {r: k for r, k in key.items() if r != bad_rid}
        v2 = [x for x in reviews if x["review_id"] != bad_rid]
        _, _, problems = mr.judge(CRIT, v2, k2, rows)
        self.assertIn("displayed claim reports/repair_terms_small/U2_B_rep1/c1 has no review row", problems)
        _, _, problems = mr.judge(CRIT, reviews + [dict(reviews[0])], key, rows)  # duplicate review row
        self.assertIn(f"review {reviews[0]['review_id']} appears more than once", problems)
        wrong = dict(key, **{bad_rid: dict(key[bad_rid], text_sha256="0" * 64)})  # mapped to another wording
        self.assertIn(f"key row {bad_rid} does not match the displayed wording", mr.judge(CRIT, reviews, wrong, rows)[2])
        moved = dict(key, **{bad_rid: dict(key[bad_rid], arm="A")})  # assigned to the wrong arm
        self.assertIn(f"key row {bad_rid} has the wrong unit/arm", mr.judge(CRIT, reviews, moved, rows)[2])
        extra = reviews + [dict(reviews[0], review_id="R999")]
        self.assertIn("review R999 is not in the key", mr.judge(CRIT, extra, key, rows)[2])

    def test_field_values_are_validated(self):
        rows, key, reviews = _fake(self.spec())
        for field, value in (("faithful", "yes"), ("term_correct", None), ("contains_known_wrong_content", "maybe"),
                             ("concepts", ["K_OTHER"]), ("concepts", "K_SWING")):
            bad = [dict(x) for x in reviews]
            bad[0][field] = value
            _, _, problems = mr.judge(CRIT, bad, key, rows)
            self.assertTrue(any(p.startswith(f"review {bad[0]['review_id']}: {field}") for p in problems), (field, value))

    def test_agreement_lists_disagreements(self):
        _, _, reviews = _fake(self.spec())
        model = [dict(x) for x in reviews]
        model[1]["faithful"] = "n"
        self.assertEqual(mr.agreement(reviews, model)["disagreements"], [(reviews[1]["review_id"], "faithful")])


class ReviewSheetTests(unittest.TestCase):
    def test_sheet_is_blind_and_seeded(self):
        rows = [dict(out=f"o{i}", unit_id="U1", arm="AB"[i % 2], claim_id="c1", text=f"t{i}", cited=[]) for i in range(6)]
        with mock.patch.object(mr, "displayed", lambda crit: (rows, [])):
            s1, k1 = mr.review_sheet(CRIT)
            s2, _ = mr.review_sheet(CRIT)
        self.assertEqual(s1, s2)
        self.assertTrue(all("arm" not in x and "unit_id" not in x and "out" not in x for x in s1))
        self.assertTrue(all(len(k["text_sha256"]) == 64 for k in k1.values()))  # key pins the wording
        self.assertEqual(sorted(k["out"] for k in k1.values()), sorted(r["out"] for r in rows))


class PlanTests(unittest.TestCase):
    def test_draft_refused_and_argument_list(self):
        self.assertEqual(CRIT["status"], "registered")
        with self.assertRaises(mv.RunAbort) as cm:  # a draft copy is refused for its status, whatever the contract
            rtr.plan(dict(CRIT, status="draft"), contract=CRIT["contract_version"])
        self.assertIn("not 'registered'", str(cm.exception))
        todo, _ = rtr.plan(CRIT, contract=CRIT["contract_version"], resume=True)
        self.assertEqual(len(todo) * 2, CRIT["calls_max"]["trial"])  # upper bound; never topped up
        argv = rtr.argv_for(todo[0], "secrets/nvidia.env")
        self.assertIsInstance(argv, list)
        self.assertEqual(argv[argv.index("--unit") + 1], "U1")
        self.assertTrue(argv[2].endswith("measure_repair.py"))


if __name__ == "__main__":
    unittest.main()
