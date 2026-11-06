"""EvidencePipeline with input checks BEFORE retrieval.

Why: EvidencePipeline.prepare() embeds the raw question with Cohere (and writes the query
cache) before the v3 planner classifies intent. A request for a personal diagnosis/dose
therefore reached a second provider and the disk before being stopped.

Order here:
  1. rag.input_guard.screen_question  -> local, no provider; redacts direct identifiers.
  2. v3 question plan only (same payload as the reader, so it shares the reader cache).
     Prohibited intents (individual_diagnosis, personalized_medication, scope_legal,
     current_services) stop here: no embedding request, no query-cache write.
  3. Otherwise the unchanged retrieval + evidence pipeline runs on the screened text.

The hash-pinned modules (evidence_pipeline, semantic_reader_v3, retriever) are not modified;
this class only changes the order of calls.
"""
from __future__ import annotations

import copy

from .evidence import EvidenceError
from .evidence_pipeline import EvidencePipeline
from .retriever import atomic_json, sha
from .semantic_reader_v3 import PLAN_SYSTEM, AtomicNeedsReader
from .input_guard import GUARD_VERSION, screen_question


class _PlanFinished(Exception):
    """Raised by the plan-only client when the reader moves past the planning stage."""


class _PlanOnlyClient:
    """Forwards question-plan requests; refuses every later stage without contacting a provider."""

    def __init__(self, inner):
        self.inner = inner

    def complete(self, messages):
        if not messages or messages[0].get("content") != PLAN_SYSTEM:
            raise _PlanFinished()
        return self.inner.complete(messages)


class GuardedEvidencePipeline(EvidencePipeline):
    def prepare(self, question, *, top_k=5, review=None, trace_path=None):
        screened = screen_question(question)
        q = screened.text
        reader = self.semantic_reader

        if review is None and isinstance(reader, AtomicNeedsReader):
            decision = self._plan_gate(reader, q)
        else:
            decision = "not_checked_reader_has_no_plan_stage"

        if decision == "blocked_before_retrieval":
            trace = self.prepare_retrieved(q, self._no_retrieval(q), review=review)
        else:
            retrieved = self.retriever.retrieve(q, top_k, include_content=True)
            trace = self.prepare_retrieved(q, retrieved, review=review)

        trace["input_guard"] = dict(
            version=GUARD_VERSION,
            decision=decision,
            intent_checked_before_retrieval=decision != "not_checked_reader_has_no_plan_stage",
            retrieval_performed=decision != "blocked_before_retrieval",
            redactions=[dict(type=k, count=n) for k, n in screened.redactions.items()],
            provider_question_sha256=sha(q),
            # Never store a hash of text that contained identifiers (hashes of phone numbers are guessable).
            original_question_sha256=None if screened.changed else sha(question.strip()),
            limitations=[
                "Names, addresses and free-text descriptions of a child are not detected or redacted.",
                "The question plan is still sent to NVIDIA before intent is known.",
                "Intent classification is made by a model; a misclassified personal request still proceeds.",
            ],
        )
        if trace_path:
            atomic_json(trace_path, trace)
        return trace

    def _plan_gate(self, reader, q):
        planner = copy.copy(reader)
        planner.client = _PlanOnlyClient(reader.client)
        try:
            planner.review(q, self._no_retrieval(q))
        except _PlanFinished:
            return "allowed"
        except EvidenceError as exc:
            # The planner accepted the question; packing sources from the empty stub failed.
            if getattr(exc, "stage", None) == "source_selection":
                return "allowed"
            raise
        # review() only returns without needing sources when the intent is prohibited.
        return "blocked_before_retrieval"

    def _no_retrieval(self, q):
        pins = getattr(self.retriever, "config", None) or {}
        return dict(
            status="ok", query=q, actual_query=q,
            collection_id=pins.get("collection_id"), space_id=pins.get("space_id"),
            strategy="not_performed_input_guard", top_k=0, results=[], query_embedding=None,
            note="Retrieval was not performed: the request type is outside the research corpus scope.",
        )
