"""Answer layer (answer_contract_v0.1 / answer_check_v0.1) with a scripted fake model. No provider calls.

Covers the 12 required cases of docs/answer_layer/DAC_TA_KIEM_TRA.md section 6, plus verifier-output
checks, the emergency placeholder, "chua_duyet" marking, the key-file rule and a real reader-v3 trace.
"""
import copy
import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from rag.answer_client import AnswerClientError, read_answer_key
from rag.answer_layer import (GEN_SYSTEM, REPAIR_SYSTEM, VERIFY_SYSTEM, AnswerError, answer_from_trace, build_catalog,
                              check_claims_k1, compute_status, parse_verification)
from rag.answer_policy import detect_emergency, load_config
from rag.answer_sources import TrustedCorpus, load_trusted_corpus
from rag.retriever import ROOT, sha

AS_OF = date(2026, 11, 7)
CFG = load_config()
T1 = "## Results\n\nSleep problems were associated with daytime behavior in the reviewed studies. " \
     "These conclusions are still premature and require further investigation in children aged 4-12."
S1 = "Sleep problems were associated with daytime behavior in the reviewed studies."
S2 = "These conclusions are still premature and require further investigation in children aged 4-12."
T2 = "Autism is known as a spectrum disorder because people with autism have a range of characteristics, needs, strengths, and challenges."
DOC1 = "P" * 100 + T1
CORPUS = TrustedCorpus.from_documents("TEST-COLL", [
    dict(id="ASD-OA-TEST1", noi_dung=DOC1, ten_tai_lieu="Sleep review",
         nguon=dict(tac_gia=["A Author", "B Author"], to_chuc=None, link_nguon="https://example.org/1", loai_nguon="research"),
         ngay_thang=dict(ngay_xuat_ban="2014-12-11", ngay_cap_nhat=None)),
    dict(id="NIH-NIMH-TEST", noi_dung=T2, ten_tai_lieu="Autism Spectrum Disorder",
         nguon=dict(tac_gia=[], to_chuc="NIMH", link_nguon="https://example.org/2", loai_nguon="official_patient_information"),
         ngay_thang=dict(ngay_xuat_ban=None, ngay_cap_nhat="Revised 2025"))],
    {"ASD-OA-TEST1": sha(DOC1), "NIH-NIMH-TEST": sha(T2)})


def _ev(eid, text, block_start, sentence):
    i = text.index(sentence)
    return dict(evidence_id=eid, start=block_start + i, end=block_start + i + len(sentence), quote=sentence)


def make_trace(*, status="sufficient", intent="general_information", needs=(("n1", "need one"),),
               question="Khó ngủ có liên quan đến hành vi ở trẻ không?", selected=("ev1", "ev2", "ev3")):
    b1 = dict(source_id="ASD-OA-TEST1", start=100, end=100 + len(T1), text=T1, content_sha256=sha(DOC1),
              metadata=dict(title="Sleep review", source=dict(tac_gia=["A Author", "B Author"], to_chuc=None,
                                                             link_nguon="https://example.org/1", loai_nguon="research"),
                            dates=dict(ngay_xuat_ban="2014-12-11", ngay_cap_nhat=None)),
              evidence=[_ev("ev1", T1, 100, S1), _ev("ev2", T1, 100, S2)])
    b2 = dict(source_id="NIH-NIMH-TEST", start=0, end=len(T2), text=T2, content_sha256=sha(T2),
              metadata=dict(title="Autism Spectrum Disorder", source=dict(tac_gia=[], to_chuc="NIMH",
                                                                         link_nguon="https://example.org/2",
                                                                         loai_nguon="official_patient_information"),
                            dates=dict(ngay_xuat_ban=None, ngay_cap_nhat="Revised 2025")),
              evidence=[_ev("ev3", T2, 0, T2)])
    blocks = [b for b in (b1, b2) if any(e["evidence_id"] in selected for e in b["evidence"])]
    return dict(question=question, question_sha256="q", retrieval=dict(collection_id="TEST-COLL"),
                medical_policy_after_selection=dict(intent=intent),
                assessment_after_selection=dict(status=status, claims=[dict(claim_id=n, text=t, required=True) for n, t in needs]),
                context_selection=dict(selected_blocks=blocks, selected_evidence_ids=list(selected)))


def claim(cid, text, ev, needs=("n1",), role="chi_tiet"):
    return dict(claim_id=cid, role=role, text=text, evidence_ids=list(ev), need_ids=list(needs))


def gen(claims, gaps=(), proposed="du"):
    return json.dumps(dict(proposed_status=proposed, claims=list(claims), gaps=list(gaps)), ensure_ascii=False)


def verdict(cid, span, support="supported", flags=()):
    return dict(claim_id=cid, support=support, flags=list(flags), evidence_span=span, explanation="")


def ver(verdicts, needs, gaps=(), uncovered=()):
    return json.dumps(dict(claims=list(verdicts), gaps=list(gaps), needs=list(needs),
                           question_parts_uncovered=list(uncovered)), ensure_ascii=False)


def need_v(nid, ok, by):
    return dict(need_id=nid, fully_addressed=ok, by_claims=list(by), missing="")


class FakeModel:
    """Returns scripted responses in order; records which system prompt each call used."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.systems = []
        self.payloads = []

    def complete(self, msgs):
        self.systems.append(msgs[0]["content"])
        self.payloads.append(json.loads(msgs[1]["content"]))
        if not self.responses:
            raise AssertionError("unexpected model call")
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return dict(content=r, cache_hit=False, elapsed_seconds=0.0, request_id="fake")

    def stages(self):
        names = {GEN_SYSTEM: "generate", REPAIR_SYSTEM: "repair", VERIFY_SYSTEM: "verify"}
        return [names[s] for s in self.systems]


C_DIRECT = claim("c1", "Chưa, tổng quan này cho rằng các kết luận vẫn còn sớm và cần nghiên cứu thêm ở trẻ 4–12 tuổi.", ["E2"],
                 role="tra_loi_truc_tiep")
C_ASSOC = claim("c2", "Các nghiên cứu được tổng quan ghi nhận khó ngủ có liên quan đến hành vi ban ngày.", ["E1"])
C_BAD = claim("c2", "Khó ngủ gây ra hành vi khó khăn ở mọi trẻ tự kỷ.", ["E1"])


def run(trace, *responses):
    model = FakeModel(*responses)
    return answer_from_trace(trace, client=model, as_of=AS_OF, corpus=CORPUS), model


class CatalogTests(unittest.TestCase):
    def test_catalog_order_ids_and_sources(self):
        cat, src = build_catalog(make_trace(), CFG, CORPUS)
        self.assertEqual(list(cat), ["E1", "E2", "E3"])
        self.assertEqual([cat[e]["evidence_id"] for e in cat], ["ev1", "ev2", "ev3"])
        self.assertEqual(src["ASD-OA-TEST1"]["year"], 2014)
        self.assertEqual(src["ASD-OA-TEST1"]["by"], "A Author và cộng sự")
        self.assertEqual(src["NIH-NIMH-TEST"]["country"], "Hoa Kỳ")
        self.assertEqual(src["NIH-NIMH-TEST"]["year"], 2025)

    def test_catalog_rejects_quote_not_matching_block(self):
        t = make_trace()
        t["context_selection"]["selected_blocks"][0]["evidence"][0]["quote"] = "Sleep problems CAUSE behavior."
        with self.assertRaises(AnswerError):
            build_catalog(t, CFG, CORPUS)

    def test_catalog_from_real_reader_v3_trace(self):
        path = ROOT / "reports/reader_refinement_20261101_232742/run_20261102_004612_154953/traces/S05.json"
        trace = json.loads(path.read_text(encoding="utf-8"))
        cat, src = build_catalog(trace, CFG, load_trusted_corpus())
        self.assertEqual([(c["source_id"], c["start"]) for c in cat.values()],
                         [("ASD-OA-PMC4271434", 38221), ("ASD-OA-PMC4271434", 45616)])
        self.assertEqual(src["ASD-OA-PMC4271434"]["year"], 2014)
        self.assertNotIn("longitudinal", cat["E1"]["quote"])  # the reader's *reason* is not part of the citable quote


class K1Tests(unittest.TestCase):
    def setUp(self):
        self.cat, self.src = build_catalog(make_trace(), CFG, CORPUS)

    def k1(self, *claims):
        return check_claims_k1(list(claims), self.cat, self.src, {"n1", "n2"}, CFG)

    def test_unknown_or_missing_evidence_ids_fail(self):  # spec 6.1, 6.2
        r = self.k1(claim("c1", "Câu có trích dẫn lạ.", ["E9"]), claim("c2", "Câu không có trích dẫn nào.", []))
        self.assertIn("invalid_evidence_ids", r["c1"])
        self.assertIn("invalid_evidence_ids", r["c2"])

    def test_dose_phone_url_fail(self):  # spec 6.11
        r = self.k1(claim("c1", "Trẻ dùng 5 mg mỗi tối.", ["E1"]), claim("c2", "Gọi 0912 345 678 để được hỗ trợ.", ["E1"]),
                    claim("c3", "Xem thêm tại https://x.org nhé.", ["E1"]))
        self.assertIn("forbidden_dose", r["c1"])
        self.assertIn("forbidden_phone", r["c2"])
        self.assertIn("forbidden_url", r["c3"])

    def test_uncited_organization_fails(self):  # spec 6.12
        r = self.k1(claim("c1", "Theo CDC, tự kỷ là một rối loạn phổ.", ["E3"]),
                    claim("c2", "Theo NIMH, tự kỷ được gọi là rối loạn phổ.", ["E3"]))
        self.assertIn("organization_not_cited:CDC", r["c1"])
        self.assertEqual(r["c2"], [])

    def test_leading_connective_and_direct_position(self):
        r = self.k1(claim("c1", "Do đó trẻ cần được hỗ trợ khác nhau.", ["E3"]),
                    claim("c2", "Không, mỗi người có đặc điểm khác nhau.", ["E3"], role="tra_loi_truc_tiep"))
        self.assertIn("leading_connective", r["c1"])
        self.assertIn("direct_answer_not_first_or_duplicate", r["c2"])

    def test_too_long_and_not_vietnamese(self):
        r = self.k1(claim("c1", " ".join(["từ"] * 61), ["E1"]), claim("c2", "Sleep problems matter a lot.", ["E1"]))
        self.assertIn("too_long", r["c1"])
        self.assertIn("not_vietnamese", r["c2"])


class VerifierOutputTests(unittest.TestCase):
    def setUp(self):
        self.cat, _ = build_catalog(make_trace(), CFG, CORPUS)
        self.needs = [dict(claim_id="n1", text="x", required=True)]

    def parse(self, content, claims):
        return parse_verification(content, claims, [], self.needs, self.cat, CFG)

    def test_span_must_be_verbatim_in_cited_quote(self):
        res = self.parse(ver([verdict("c2", "Sleep problems cause behavior problems in all children.")], []), [C_ASSOC])
        self.assertIn("span_not_in_cited_evidence", res["claims"]["c2"]["reasons"])
        ok = self.parse(ver([verdict("c2", S1)], []), [C_ASSOC])
        self.assertEqual(ok["claims"]["c2"]["reasons"], [])

    def test_span_from_uncited_quote_fails(self):
        res = self.parse(ver([verdict("c2", S2)], []), [C_ASSOC])  # S2 is E2, claim cites only E1
        self.assertIn("span_not_in_cited_evidence", res["claims"]["c2"]["reasons"])

    def test_missing_verdict_fails_claim_unknown_id_is_error(self):
        res = self.parse(ver([], []), [C_ASSOC])
        self.assertIn("verdict_missing", res["claims"]["c2"]["reasons"])
        with self.assertRaises(AnswerError):
            self.parse(ver([verdict("c9", S1)], []), [C_ASSOC])
        with self.assertRaises(AnswerError):
            self.parse(ver([verdict("c2", S1, flags=["made_up_flag"])], []), [C_ASSOC])

    def test_need_credited_to_failed_claim_is_not_addressed(self):  # conservative coverage
        claims = [C_DIRECT, C_ASSOC]
        status, addressed, missing = compute_status(reader_status="sufficient", claims=claims, passing={"c1"},
                                                    need_verdicts={"n1": need_v("n1", True, ["c1", "c2"])},
                                                    needs=self.needs, uncovered=[])
        self.assertEqual((status, addressed, missing), ("khong_du", [], ["n1"]))


class FlowTests(unittest.TestCase):
    def test_happy_path_two_calls_render_notes_and_marking(self):
        r, m = run(make_trace(), gen([C_DIRECT, C_ASSOC]),
                   ver([verdict("c1", S2), verdict("c2", S1)], [need_v("n1", True, ["c1", "c2"])]))
        self.assertEqual(m.stages(), ["generate", "verify"])
        self.assertEqual((r["route"], r["status"], r["repairs"]), ("answer", "du", 0))
        text = r["render"]["text"]
        self.assertTrue(text.startswith(CFG["dev_banner"]))
        self.assertIn(C_DIRECT["text"] + " [1]", text)
        self.assertIn("Nguồn [1] có năm tài liệu là 2014", text)
        self.assertIn(CFG["source_notes"]["single_source_note"], text)
        self.assertIn(CFG["disclaimer"]["text"], text)
        self.assertIn(f'Đoạn được dùng: "{S2}"', text)
        self.assertEqual(r["review_status"], "chua_duyet")
        self.assertIn(CFG["verifier_same_model_limitation"], r["limitations"])
        self.assertNotIn("Revised", json.dumps(m.payloads[0]))  # model sees labels/quotes only

    def test_failed_claim_persisting_after_repair_is_removed(self):  # spec 6.3
        bad_v = [verdict("c1", S2), verdict("c2", S1, "partially_supported", ["certainty_changed"])]
        r, m = run(make_trace(), gen([C_DIRECT, C_BAD]), ver(bad_v, [need_v("n1", True, ["c1"])]),
                   gen([C_DIRECT, C_BAD]), ver(bad_v, [need_v("n1", True, ["c1"])]))
        self.assertEqual(m.stages(), ["generate", "verify", "repair", "verify"])
        self.assertEqual((r["status"], r["repairs"]), ("du", 1))
        self.assertNotIn(C_BAD["text"], r["render"]["text"])
        self.assertEqual([c["claim_id"] for c in r["claims_final"]], ["c1"])
        self.assertTrue(any(x["claim_id"] == "c2" and "flag_certainty_changed" in x["reasons"] and x["round"] == "repair"
                            for x in r["claims_removed"]))
        self.assertEqual(m.payloads[2]["problems"][0]["claim_id"], "c2")

    def test_everything_fails_after_repair_gives_khong_du_without_claim_text(self):  # spec 6.4
        bad = [verdict("c1", S2, "not_supported"), verdict("c2", S1, "contradicted")]
        r, _ = run(make_trace(), gen([C_DIRECT, C_BAD]), ver(bad, [need_v("n1", False, [])]),
                   gen([C_DIRECT, C_BAD]), ver(bad, [need_v("n1", False, [])]))
        self.assertEqual(r["status"], "khong_du")
        self.assertIn(CFG["status_openers"]["khong_du"], r["render"]["text"])
        for c in (C_DIRECT, C_BAD):
            self.assertNotIn(c["text"], r["render"]["text"])
        self.assertEqual(r["claims_final"], [])
        self.assertNotIn("Nguồn:", r["render"]["text"])
        self.assertNotIn(CFG["disclaimer"]["text"], r["render"]["text"])
        self.assertIn(CFG["disclaimer_no_content"]["text"], r["render"]["text"])

    def test_reader_partial_caps_status(self):  # spec 6.5
        r, _ = run(make_trace(status="partially_sufficient"), gen([C_DIRECT]),
                   ver([verdict("c1", S2)], [need_v("n1", True, ["c1"])]))
        self.assertEqual(r["status"], "mot_phan")

    def test_uncovered_question_part_prevents_du(self):  # spec 6.6
        r, _ = run(make_trace(), gen([C_DIRECT]),
                   ver([verdict("c1", S2)], [need_v("n1", True, ["c1"])], uncovered=["có liên quan đến hành vi"]))
        self.assertEqual(r["status"], "mot_phan")
        self.assertIn(CFG["gap_sentence_generic"], r["render"]["text"])

    def test_invalid_repair_output_is_system_error_not_khong_du(self):  # spec 6.7
        r, _ = run(make_trace(), gen([C_DIRECT, C_BAD]),
                   ver([verdict("c1", S2), verdict("c2", S1, "contradicted")], [need_v("n1", True, ["c1"])]),
                   "{not json")
        self.assertEqual((r["route"], r["error"], r["status"]), ("system_error", "gen_schema", None))
        self.assertIn(CFG["system_error_text"], r["render"]["text"])
        self.assertNotIn(CFG["status_openers"]["khong_du"], r["render"]["text"])
        self.assertNotIn(C_DIRECT["text"], r["render"]["text"])

    def test_policy_intent_uses_template_without_model(self):  # spec 6.8
        r, m = run(make_trace(intent="personalized_medication", status="insufficient", selected=()))
        self.assertEqual((r["route"], m.systems), ("policy", []))
        self.assertIn(CFG["policy_templates"]["personalized_medication"]["text"], r["render"]["text"])
        self.assertIn(CFG["disclaimer_no_content"]["text"], r["render"]["text"])
        self.assertNotIn(CFG["disclaimer"]["text"], r["render"]["text"])  # nothing is cited here
        self.assertEqual(r["template_review_status"], "chua_duyet")

    def test_empty_catalog_gives_khong_du_without_model(self):  # spec 6.9
        r = answer_from_trace(make_trace(status="insufficient", selected=()), client=None, as_of=AS_OF, corpus=CORPUS)
        self.assertEqual((r["route"], r["status"], r["calls"]), ("answer", "khong_du", []))

    def test_render_is_deterministic_and_numbered_by_first_citation(self):  # spec 6.10
        c_nimh = claim("c1", "Theo NIMH, tự kỷ được gọi là rối loạn phổ vì mỗi người có đặc điểm, nhu cầu, điểm mạnh và khó khăn khác nhau.",
                       ["E3"], role="tra_loi_truc_tiep")
        script = (gen([c_nimh, C_ASSOC]), ver([verdict("c1", T2), verdict("c2", S1)], [need_v("n1", True, ["c1", "c2"])]))
        a, _ = run(make_trace(), *script)
        b, _ = run(make_trace(), *script)
        self.assertEqual(a["render"]["text"].encode("utf-8"), b["render"]["text"].encode("utf-8"))
        self.assertEqual([s["source_id"] for s in a["render"]["sources"]], ["NIH-NIMH-TEST", "ASD-OA-TEST1"])
        self.assertIn("Nguồn [1] được soạn cho bối cảnh Hoa Kỳ.", a["render"]["text"])

    def test_provider_error_during_verification_is_system_error(self):
        r, _ = run(make_trace(), gen([C_DIRECT]), AnswerClientError("nim_network"))
        self.assertEqual((r["route"], r["error"]), ("system_error", "nim_network"))
        self.assertNotIn(C_DIRECT["text"], r["render"]["text"])
        self.assertIn("generate", r["timings"])

    def test_invalid_first_output_triggers_one_repair(self):
        r, m = run(make_trace(), "not json", gen([C_DIRECT]), ver([verdict("c1", S2)], [need_v("n1", True, ["c1"])]))
        self.assertEqual(m.stages(), ["generate", "repair", "verify"])
        self.assertEqual((r["status"], r["repairs"]), ("du", 1))

    def test_no_verifier_call_when_nothing_passes_k1(self):
        bad = claim("c1", "Câu trích dẫn sai.", ["E9"])
        r, m = run(make_trace(), gen([bad]), gen([bad]))
        self.assertEqual(m.stages(), ["generate", "repair"])
        self.assertEqual(r["status"], "khong_du")

    def test_gap_topic_with_assertion_is_replaced_by_generic_sentence(self):
        t = make_trace(needs=(("n1", "a"), ("n2", "b")))
        gaps = [dict(need_id="n2", topic_vi="melatonin giúp trẻ ngủ ngon hơn")]
        r, _ = run(t, gen([C_DIRECT], gaps, "mot_phan"),
                   ver([verdict("c1", S2)], [need_v("n1", True, ["c1"]), need_v("n2", False, [])],
                       gaps=[dict(need_id="n2", contains_claim=True)]))
        self.assertEqual(r["status"], "mot_phan")
        self.assertNotIn("melatonin", r["render"]["text"])
        self.assertIn(CFG["gap_sentence_generic"], r["render"]["text"])

    def test_valid_gap_topic_is_listed(self):
        t = make_trace(needs=(("n1", "a"), ("n2", "b")))
        gaps = [dict(need_id="n2", topic_vi="việc gia đình tiếp tục nói chuyện với trẻ")]
        r, _ = run(t, gen([C_DIRECT], gaps, "mot_phan"),
                   ver([verdict("c1", S2)], [need_v("n1", True, ["c1"]), need_v("n2", False, [])],
                       gaps=[dict(need_id="n2", contains_claim=False)]))
        self.assertIn(CFG["gap_sentence_prefix"] + "việc gia đình tiếp tục nói chuyện với trẻ.", r["render"]["text"])


class EmergencyAndMarkingTests(unittest.TestCase):
    def test_emergency_phrases(self):
        self.assertTrue(detect_emergency("Tôi không chịu nổi nữa, muốn kết thúc tất cả."))
        self.assertTrue(detect_emergency("con toi khong muon song nua"))
        for q in ("Quy trình đánh giá tự kỷ gồm những bước nào?", "Bé bị đánh giá chậm nói thì sao?",
                  "Dạy trẻ từ từ có tốt không?", "Trẻ tự kỷ có hay tự xoay vòng không?"):
            self.assertEqual(detect_emergency(q), [], q)

    def test_emergency_route_never_calls_model_or_shows_other_content(self):
        r, m = run(make_trace(question="Tôi muốn chết, phải làm sao?"))
        self.assertEqual((r["route"], m.systems), ("emergency", []))
        self.assertEqual(r["render"]["text"], CFG["dev_banner"] + "\n" + CFG["emergency"]["placeholder"] + "\n")

    def test_config_must_stay_marked_unreviewed(self):
        for t in CFG["policy_templates"].values():
            self.assertEqual(t["review_status"], "chua_duyet")
        changed = copy.deepcopy(CFG)
        changed["review_status"] = "da_duyet"
        with self.assertRaises(ValueError):
            load_config(changed)

    def test_key_file_rule(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            for bad in (Path("C:/Users/someone/.continue/config.yaml"), ROOT / ".env", ROOT / "README.md"):
                with self.assertRaises(AnswerClientError) as ctx:
                    read_answer_key(bad)
                self.assertEqual(ctx.exception.code, "key_file_refused")
        with mock.patch.dict(os.environ, {"NVIDIA_API_KEY": "nvapi-test"}, clear=True):
            self.assertEqual(read_answer_key(), "nvapi-test")


S05_PATH = ROOT / "reports/reader_refinement_20261101_232742/run_20261102_004612_154953/traces/S05.json"


class ProvenanceTests(unittest.TestCase):
    """P1 (review 07/11): a trace edited consistently (block + quote) must not be accepted."""

    def setUp(self):
        self.trace = json.loads(S05_PATH.read_text(encoding="utf-8"))
        self.corpus = load_trusted_corpus()

    def test_consistent_edit_of_block_and_quote_is_rejected(self):
        t = copy.deepcopy(self.trace)
        block = t["context_selection"]["selected_blocks"][0]
        ev = block["evidence"][0]
        i = ev["start"] - block["start"] + 10  # one character inside the first evidence quote
        old = block["text"][i]
        new = "X" if old != "X" else "Y"
        block["text"] = block["text"][:i] + new + block["text"][i + 1:]
        j = i - (ev["start"] - block["start"])
        ev["quote"] = ev["quote"][:j] + new + ev["quote"][j + 1:]
        self.assertEqual(block["text"][ev["start"] - block["start"]:ev["end"] - block["start"]], ev["quote"])  # internally consistent
        with self.assertRaises(AnswerError) as ctx:
            build_catalog(t, CFG, self.corpus)
        self.assertEqual(ctx.exception.code, "catalog_provenance")
        r = answer_from_trace(t, client=FakeModel(), as_of=AS_OF)
        self.assertEqual((r["route"], r["error"]), ("system_error", "catalog_provenance"))

    def test_edit_outside_quotes_is_rejected(self):
        t = copy.deepcopy(self.trace)
        block = t["context_selection"]["selected_blocks"][0]
        first = min(e["start"] for e in block["evidence"]) - block["start"]
        self.assertGreater(first, 0)
        i = first - 1  # a character of the block before the first evidence quote
        block["text"] = block["text"][:i] + ("X" if block["text"][i] != "X" else "Y") + block["text"][i + 1:]
        with self.assertRaises(AnswerError) as ctx:
            build_catalog(t, CFG, self.corpus)
        self.assertEqual(ctx.exception.code, "catalog_provenance")

    def test_tampered_hash_offsets_or_collection_are_rejected(self):
        for mutate in (lambda b, t: b.__setitem__("content_sha256", "0" * 64),
                       lambda b, t: b["evidence"][0].__setitem__("end", b["evidence"][0]["end"] + 1),
                       lambda b, t: t["retrieval"].__setitem__("collection_id", "another_collection")):
            t = copy.deepcopy(self.trace)
            mutate(t["context_selection"]["selected_blocks"][0], t)
            with self.assertRaises(AnswerError):
                build_catalog(t, CFG, self.corpus)

    def test_metadata_comes_from_corpus_not_trace(self):
        t = copy.deepcopy(self.trace)
        for b in t["context_selection"]["selected_blocks"]:
            b["metadata"]["title"] = "Forged title"
            b["metadata"]["source"]["link_nguon"] = "https://forged.example"
        _, src = build_catalog(t, CFG, self.corpus)
        self.assertTrue(src["ASD-OA-PMC4271434"]["title"].startswith("The relationship between sleep and behavior"))
        self.assertEqual(src["ASD-OA-PMC4271434"]["url"], "https://pmc.ncbi.nlm.nih.gov/articles/PMC4271434/")


class ConfigMarkingTests(unittest.TestCase):
    """P2 (review 07/11): every component must stay chua_duyet, not only the top level."""

    def test_any_component_marked_reviewed_is_rejected(self):
        paths = [("policy_templates", "individual_diagnosis"), ("policy_templates", "scope_legal"), ("disclaimer",),
                 ("disclaimer_no_content",),
                 ("emergency",), ("source_notes",)]
        for path in paths:
            for value in ("da_duyet", None):
                cfg = copy.deepcopy(CFG)
                node = cfg
                for k in path:
                    node = node[k]
                if value is None:
                    del node["review_status"]
                else:
                    node["review_status"] = value
                with self.assertRaises(ValueError, msg=f"{path} {value}"):
                    load_config(cfg)

    def test_new_component_marked_reviewed_and_missing_template_are_rejected(self):
        cfg = copy.deepcopy(CFG)
        cfg["extra"] = {"review_status": "da_duyet", "text": "x"}
        with self.assertRaises(ValueError):
            load_config(cfg)
        cfg = copy.deepcopy(CFG)
        del cfg["policy_templates"]["unclassified"]
        with self.assertRaises(ValueError):
            load_config(cfg)


class ScopeWordingTests(unittest.TestCase):
    """P3 (review 07/11): status templates must not claim more than this retrieval checked."""

    def test_status_templates_speak_about_this_retrieval_only(self):
        for text in (CFG["status_openers"]["mot_phan"], CFG["status_openers"]["khong_du"],
                     CFG["gap_sentence_prefix"], CFG["gap_sentence_generic"]):
            self.assertIn("đã truy xuất và kiểm tra ở lượt này", text)
        for text in [CFG["status_openers"]["khong_du"], CFG["gap_sentence_prefix"], CFG["gap_sentence_generic"],
                     CFG["system_error_text"]] + [t["text"] for t in CFG["policy_templates"].values()]:
            # no sentence may START with a claim about the whole corpus ("Tài liệu trong kho chưa…", "Kho tài liệu không…")
            self.assertNotRegex(text, r"(?i)(^|[.!?]\s+)(tài liệu (hiện có )?trong kho|kho tài liệu)\s")


if __name__ == "__main__":
    unittest.main()
