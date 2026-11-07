"""Deterministic gate for unrequested pharmacological content (pharm_gate_v0.1). No provider calls."""
import copy
import json
import unittest

from rag.answer_pharm import PharmGate, load_pharm_gate
from rag.retriever import ROOT
from tests.test_answer_layer import (C_DIRECT, S2, claim, gen, make_trace, need_v, run, ver, verdict)

GATE = load_pharm_gate()
Q_SLEEP = "Khó ngủ có liên quan đến hành vi ở trẻ tự kỷ, nhưng đã đủ để kết luận quan hệ nhân quả hai chiều chắc chắn chưa?"
Q_H03 = "Khi thấy triệu chứng đã đỡ, gia đình có nên tự dừng thuốc đang được bác sĩ kê cho trẻ không?"


def blocked(question, text):
    return GATE.check(text, GATE.scope(question))


class GateTermTests(unittest.TestCase):
    def test_f11_unrequested_drug_name_is_blocked(self):
        self.assertEqual(blocked(Q_SLEEP, "Melatonin là một phương pháp điều trị giấc ngủ hiệu quả cho trẻ tự kỷ."),
                         ["pharm_unrequested:drug_name:melatonin"])
        self.assertTrue(blocked(Q_SLEEP, "Các phương pháp điều trị bằng thuốc giúp trẻ ngủ tốt hơn."))

    def test_core_intervention_wording_is_not_pharmacological(self):
        for text in ("Can thiệp hành vi do cha mẹ thực hiện giúp cải thiện thời gian vào giấc ở trẻ tự kỷ chức năng cao.",
                     "Điều trị rối loạn giấc ngủ ở một nhóm trẻ tự kỷ giúp cải thiện triệu chứng cốt lõi.",
                     "Liệu pháp tích hợp cảm giác Ayres được điều chỉnh riêng cho từng trẻ.",
                     "Mẹ hút thuốc lá khi mang thai được xem xét trong một số nghiên cứu."):
            self.assertEqual(blocked(Q_SLEEP, text), [], text)

    def test_medication_question_allows_generic_and_dosing_but_not_other_drug_names(self):
        for text in ("Người bệnh không nên tự ngừng thuốc được kê đơn ngay cả khi cảm thấy đỡ.",
                     "Người cung cấp dịch vụ y tế có thể điều chỉnh kế hoạch điều trị để giảm liều thuốc từ từ và an toàn.",
                     "Ngừng thuốc quá sớm có thể gây tác dụng phụ khó chịu hoặc có hại."):
            self.assertEqual(blocked(Q_H03, text), [], text)
        self.assertEqual(blocked(Q_H03, "Risperidone có thể được giảm liều từ từ."), ["pharm_unrequested:drug_name:risperidone"])

    def test_same_drug_named_in_question_is_allowed_others_are_not(self):
        q = "Melatonin có giúp trẻ tự kỷ ngủ ngon hơn không?"
        self.assertEqual(blocked(q, "Một nghiên cứu ghi nhận melatonin là phương pháp điều trị giấc ngủ hiệu quả cho trẻ tự kỷ."), [])
        self.assertEqual(blocked(q, "Thuốc an thần cũng được dùng cho trẻ."), [])  # melatonin question = medication question
        self.assertEqual(blocked(q, "Risperidon cũng được dùng cho trẻ."), ["pharm_unrequested:drug_name:risperidone"])

    def test_negated_mentions_do_not_open_permission(self):
        for q in ("Tôi không hỏi về thuốc, chỉ muốn biết cách giúp trẻ ngủ ngon hơn?",
                  "Có cách nào giúp trẻ tự kỷ ngủ ngon mà không dùng thuốc không?",
                  "Ngoài thuốc ra thì gia đình có thể làm gì để trẻ ngủ tốt hơn?",
                  "Thay vì dùng thuốc, cha mẹ có thể làm gì khi trẻ khó ngủ?"):
            scope = GATE.scope(q)
            self.assertFalse(scope["medication"], q)
            self.assertIn("thuốc", scope["negated_mentions"], q)
            self.assertTrue(GATE.check("Thuốc ngủ có thể giúp trẻ vào giấc nhanh hơn.", scope), q)

    def test_supplements_need_a_supplement_question(self):
        q = "Trẻ tự kỷ có cần bổ sung vitamin D không?"
        self.assertEqual(blocked(q, "Một số nghiên cứu xem xét việc bổ sung vitamin cho trẻ tự kỷ."), [])
        self.assertEqual(blocked(q, "Thuốc an thần giúp trẻ bình tĩnh."), ["pharm_unrequested:drug_class:thuốc an thần",
                                                                           "pharm_unrequested:medication_generic:thuốc"])
        self.assertEqual(blocked(Q_SLEEP, "Bổ sung omega-3 có thể có ích."), ["pharm_unrequested:supplement:omega-3"])

    def test_accentless_question_opens_no_permission(self):  # documented conservative limitation
        self.assertFalse(GATE.scope("co nen cho con uong thuoc ngu khong")["medication"])

    def test_term_list_must_stay_unreviewed(self):
        data = json.loads((ROOT / "deployments/answer_pharm_gate.json").read_text(encoding="utf-8"))
        PharmGate(data)
        bad = copy.deepcopy(data)
        bad["review_status"] = "da_duyet"
        with self.assertRaises(ValueError):
            PharmGate(bad)


class GateFlowTests(unittest.TestCase):
    """The gate runs in K1 of every round; a blocked claim is never sent to the verifier and never rendered."""
    C_MEL = claim("c2", "Melatonin giúp trẻ ngủ tốt hơn theo các nghiên cứu được tổng quan.", ["E1"])

    def test_blocked_in_both_rounds_and_never_rendered(self):
        trace = make_trace(question=Q_SLEEP)
        r, m = run(trace, gen([C_DIRECT, self.C_MEL]), ver([verdict("c1", S2)], [need_v("n1", True, ["c1"])]),
                   gen([C_DIRECT, self.C_MEL]), ver([verdict("c1", S2)], [need_v("n1", True, ["c1"])]))
        self.assertEqual(m.stages(), ["generate", "verify", "repair", "verify"])
        for payload in (m.payloads[1], m.payloads[3]):  # verifier payloads
            self.assertEqual([c["claim_id"] for c in payload["claims"]], ["c1"])
        self.assertIn("pharm_unrequested:drug_name:melatonin", m.payloads[2]["problems"][0]["reasons"])
        got = [(x["round"], x["disposition"], x["claim_id"]) for x in r["claims_removed"] if x["claim_id"] == "c2"]
        self.assertEqual(got, [("generate", "blocked_pharm_gate", "c2"), ("repair", "blocked_pharm_gate", "c2")])
        self.assertNotIn("elatonin", json.dumps(r["render"], ensure_ascii=False))
        self.assertEqual(r["pharm_gate"]["gate_version"], "pharm_gate_v0.1")
        self.assertEqual(r["status"], "du")

    def test_blocked_only_claim_gives_khong_du(self):
        trace = make_trace(question=Q_SLEEP)
        r, m = run(trace, gen([claim("c1", self.C_MEL["text"], ["E1"])]), gen([claim("c1", self.C_MEL["text"], ["E1"])]))
        self.assertEqual(m.stages(), ["generate", "repair"])  # nothing passes K1 -> no verifier call
        self.assertEqual((r["status"], r["claims_final"]), ("khong_du", []))
        self.assertNotIn("elatonin", r["render"]["text"])

    def test_gap_topic_with_unrequested_drug_is_dropped_before_verification(self):
        trace = make_trace(question=Q_SLEEP, needs=(("n1", "a"), ("n2", "b")))
        gaps = [dict(need_id="n2", topic_vi="hiệu quả của melatonin")]
        r, m = run(trace, gen([C_DIRECT], gaps, "mot_phan"),
                   ver([verdict("c1", S2)], [need_v("n1", True, ["c1"]), need_v("n2", False, [])]))
        self.assertEqual(m.payloads[1]["gaps"], [])
        self.assertNotIn("elatonin", r["render"]["text"])

    def test_medication_question_claim_passes_gate(self):
        trace = make_trace(question=Q_H03)
        c = claim("c1", "Theo tổng quan, các kết luận về thuốc ngủ ở trẻ 4–12 tuổi vẫn còn sớm.", ["E2"], role="tra_loi_truc_tiep")
        r, m = run(trace, gen([c]), ver([verdict("c1", S2)], [need_v("n1", True, ["c1"])]))
        self.assertEqual((r["status"], len(r["claims_final"])), ("du", 1))
        self.assertTrue(r["pharm_gate"]["medication"])


if __name__ == "__main__":
    unittest.main()
