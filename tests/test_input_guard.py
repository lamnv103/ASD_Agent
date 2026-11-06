"""Input checks must run before any retrieval/embedding provider call."""
import json
import unittest

from rag.evidence import EvidenceError
from rag.guarded_pipeline import GuardedEvidencePipeline
from rag.input_guard import MAX_QUESTION_CHARS, screen_question
from rag.semantic_reader_v3 import PLAN_SYSTEM, AtomicNeedsReader
from test_evidence_context import QUESTION, FixtureCounter, config, document
from test_semantic_reader import ReaderCounter
from test_semantic_reader_v3 import cfg, plan


def record(d):
    return dict(content=json.dumps(d), cache_hit=True, prompt_token_delta=0)


class RecordingRetriever:
    """Fails the test if retrieval happens when it must not."""

    config = dict(collection_id="TEST-COLLECTION", space_id="TEST-SPACE")

    def __init__(self, forbid=False):
        self.queries = []
        self.forbid = forbid

    def retrieve(self, query, top_k=5, *, include_content=True):
        if self.forbid:
            raise AssertionError("Retrieval/embedding provider must not be called")
        self.queries.append(query)
        return dict(status="ok", query=query, actual_query=query, collection_id="TEST-COLLECTION",
                    space_id="TEST-SPACE", results=[document()])


class PlanThenStopClient:
    """Answers the plan; any later stage is a test failure unless allowed."""

    def __init__(self, plan_record, later=None):
        self.plan_record = plan_record
        self.later = list(later or [])
        self.messages = []

    def complete(self, messages):
        self.messages.append(messages)
        if messages[0]["content"] == PLAN_SYSTEM:
            return self.plan_record
        if not self.later:
            raise AssertionError("Unexpected reader stage")
        return self.later.pop(0)


def pipeline(client, retriever):
    reader = AtomicNeedsReader(cfg(), counter=ReaderCounter(), client=client)
    return GuardedEvidencePipeline(retriever=retriever, config=config(), counter=FixtureCounter(),
                                   semantic_reader=reader)


class ScreenTests(unittest.TestCase):
    def test_redacts_direct_identifiers_and_reports_only_counts(self):
        s = screen_question("Con tôi sinh 12/03/2019, SĐT 0912 345 678, email me@example.com, CCCD 001234567890.")
        self.assertNotIn("0912", s.text)
        self.assertNotIn("me@example.com", s.text)
        self.assertNotIn("001234567890", s.text)
        self.assertNotIn("12/03/2019", s.text)
        self.assertEqual(s.redactions, dict(email=1, phone=1, national_id=1, full_date=1))

    def test_every_supported_full_date_form_is_redacted(self):
        for raw in ["12/03/2019", "12-3-2019", "12.03.2019", "2019-03-12", "2019/3/12", "2019.03.12",
                    "ngày 12 tháng 3 năm 2019", "Ngày 2 tháng 11 năm 2020", "12 tháng 3, năm 2019"]:
            s = screen_question(f"Con tôi sinh {raw}, có cần đánh giá không?")
            self.assertIn("[NGÀY]", s.text, raw)
            self.assertNotRegex(s.text, r"2019|2020", raw)
            self.assertEqual(s.redactions, dict(full_date=1), raw)

    def test_numbers_that_are_not_full_dates_are_kept(self):
        q = ("Bé 3 tuổi, năm 2019 mới chuyển nhà, tổng quan 2015–2024 và 2015-2024 nói gì? "
             "Sinh tháng 3/2019, điểm 12/30, cân nặng 15.5 kg, 2 tháng 3 lần.")
        s = screen_question(q)
        self.assertEqual(s.text, q)
        self.assertFalse(s.changed)

    def test_ordinary_question_is_unchanged(self):
        q = "Trẻ 3 tuổi chưa nói được nhiều từ có cần đánh giá phát triển không? Năm 2025 có hướng dẫn mới không?"
        s = screen_question(q)
        self.assertEqual(s.text, q)
        self.assertFalse(s.changed)

    def test_rejects_empty_non_text_and_overlong_input(self):
        for bad in ["", "   \x00 ", None, "a" * (MAX_QUESTION_CHARS + 1)]:
            with self.assertRaises(EvidenceError) as caught:
                screen_question(bad)
            self.assertEqual(caught.exception.code, "input_rejected")


class GuardedPipelineTests(unittest.TestCase):
    def test_prohibited_intent_stops_before_retrieval(self):
        p = plan()
        p["intent"] = "personalized_medication"
        client = PlanThenStopClient(record(p))
        trace = pipeline(client, RecordingRetriever(forbid=True)).prepare(QUESTION)
        self.assertEqual(trace["input_guard"]["decision"], "blocked_before_retrieval")
        self.assertFalse(trace["input_guard"]["retrieval_performed"])
        self.assertEqual(trace["retrieval"]["sources"], [])
        self.assertEqual(trace["assessment_after_selection"]["status"], "insufficient")
        self.assertEqual(trace["context_selection"]["selected_blocks"], [])
        self.assertTrue(all(m[0]["content"] == PLAN_SYSTEM for m in client.messages))
        self.assertFalse(trace["generation_enabled"])

    def test_allowed_intent_retrieves_and_plan_payload_matches_reader(self):
        client = PlanThenStopClient(record(plan()))  # no answer for later stages
        retriever = RecordingRetriever()
        guarded = pipeline(client, retriever)
        # Reaching the selection stage raises in the fake client; by then retrieval must have happened.
        with self.assertRaises(AssertionError):
            guarded.prepare(QUESTION)
        self.assertEqual(retriever.queries, [QUESTION])
        plans = [m for m in client.messages if m[0]["content"] == PLAN_SYSTEM]
        self.assertEqual(len(plans), 2)
        self.assertEqual(plans[0], plans[1], "Gate and reader must send an identical plan payload (shared cache)")

    def test_only_redacted_text_reaches_retrieval_and_plan(self):
        question = QUESTION + " Gọi 0912345678."
        p = plan()
        p["needs"][0]["anchor"] = QUESTION
        client = PlanThenStopClient(record(p))
        retriever = RecordingRetriever()
        with self.assertRaises(AssertionError):
            pipeline(client, retriever).prepare(question)
        self.assertEqual(len(retriever.queries), 1)
        self.assertNotIn("0912345678", retriever.queries[0])
        self.assertTrue(all("0912345678" not in json.dumps(m, ensure_ascii=False) for m in client.messages))

    def test_plan_failure_never_falls_through_to_retrieval(self):
        client = PlanThenStopClient(record(dict(intent="not-an-intent", needs=[], required_personal_information=[])))
        with self.assertRaises(EvidenceError):
            pipeline(client, RecordingRetriever(forbid=True)).prepare(QUESTION)

    def test_fails_closed_without_reader_v3(self):
        # Default constructor (no reader) and a reader of another type must not reach retrieval.
        for reader in [None, object()]:
            p = GuardedEvidencePipeline(retriever=RecordingRetriever(forbid=True), config=config(),
                                        counter=FixtureCounter(), semantic_reader=reader)
            with self.assertRaises(EvidenceError) as caught:
                p.prepare("Con tôi có bị tự kỷ không?")
            self.assertEqual(caught.exception.code, "input_guard_unavailable")

    def test_explicit_review_requires_explicit_unchecked_mode(self):
        client = PlanThenStopClient(record(plan()))
        p = pipeline(client, RecordingRetriever(forbid=True))
        with self.assertRaises(EvidenceError) as caught:
            p.prepare(QUESTION, review=dict(reviewer=dict(kind="test_fixture")))
        self.assertEqual(caught.exception.code, "input_guard_unavailable")
        self.assertEqual(client.messages, [])

    def test_unchecked_mode_is_opt_in_and_recorded(self):
        retriever = RecordingRetriever()
        p = GuardedEvidencePipeline(retriever=retriever, config=config(), counter=FixtureCounter(),
                                    allow_unchecked_retrieval=True)
        p.prepare_retrieved = lambda q, retrieved, review=None: {}
        trace = p.prepare(QUESTION)
        self.assertEqual(retriever.queries, [QUESTION])
        self.assertEqual(trace["input_guard"]["decision"], "unchecked_explicitly_allowed")
        self.assertFalse(trace["input_guard"]["intent_checked_before_retrieval"])

    def test_rejected_input_contacts_nobody(self):
        client = PlanThenStopClient(record(plan()))
        with self.assertRaises(EvidenceError):
            pipeline(client, RecordingRetriever(forbid=True)).prepare("   ")
        self.assertEqual(client.messages, [])


if __name__ == "__main__":
    unittest.main()
