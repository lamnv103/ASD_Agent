"""Cache-only replay: the input guard must not change any accepted v3 result.

For each of the 23 accepted reader-v3 traces:
  * GuardedEvidencePipeline.prepare() reproduces assessment, context and policy exactly;
  * prohibited-intent questions are now stopped before retrieval (no embedding request);
  * every other question retrieves the same five sources as the original trace.
No provider call is possible (key suppliers raise). Output goes to a new verification run folder.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/evaluation"))
from audit_output import new_run_dir  # noqa: E402
from evaluate_retriever import snapshot  # noqa: E402
from verify_reader_v3 import stable_comparison  # noqa: E402

from rag.guarded_pipeline import GuardedEvidencePipeline  # noqa: E402
from rag.input_guard import is_nfc, screen_question  # noqa: E402
from rag.retriever import PostgresRetriever, atomic_json  # noqa: E402
from rag.semantic_reader_v3 import AtomicNeedsReader  # noqa: E402

BLOCKED = {"individual_diagnosis", "personalized_medication", "scope_legal", "current_services"}


def _without_excluded(trace):
    copy = dict(trace)
    copy["context_selection"] = {k: v for k, v in trace["context_selection"].items() if k != "excluded"}
    return copy


def no_api():
    raise AssertionError("Cache miss: provider access is prohibited during this audit")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    work = ROOT / (ROOT / "reports/.reader_refinement_current_run").read_text(encoding="utf-8").strip()
    runs = json.loads((work / "evaluation_selection.json").read_text(encoding="utf-8"))["runs"]
    retriever = PostgresRetriever(key_supplier=no_api)
    before = snapshot(retriever)
    pipe = GuardedEvidencePipeline(retriever)
    pipe.semantic_reader = AtomicNeedsReader(counter=pipe.counter, key_supplier=no_api)
    out = new_run_dir("guarded_pipeline")
    rows = []
    for name in runs:
        folder = ROOT / name
        for row in json.loads((folder / "summary.json").read_text(encoding="utf-8"))["results"]:
            qid, question = row["question_id"], row["question"]
            original = json.loads((folder / "traces" / f"{qid}.json").read_text(encoding="utf-8"))
            assert not screen_question(question).changed, (qid, "evaluation question unexpectedly redacted")
            trace = pipe.prepare(question)
            guard = trace["input_guard"]
            intent = original["semantic_reader"]["review"]["intent"]
            if intent in BLOCKED:
                # Only expected difference: the original listed retrieved-but-unread passages as
                # excluded ("not_semantically_reviewed"); nothing is retrieved now, so nothing is excluded.
                old_excluded = original["context_selection"]["excluded"]
                assert all(e["reason"] == "not_semantically_reviewed" for e in old_excluded), qid
                assert trace["context_selection"]["excluded"] == [], qid
                stable_comparison(_without_excluded(trace), _without_excluded(original))
                assert guard["decision"] == "blocked_before_retrieval", qid
                assert trace["retrieval"]["sources"] == [] and trace["retrieval"]["query_embedding"] is None, qid
            else:
                stable_comparison(trace, original)
                assert guard["decision"] == "allowed", qid
                assert trace["retrieval"]["sources"] == original["retrieval"]["sources"], qid
            assert all(c["cache_hit"] for c in trace["semantic_reader"]["calls"]), qid
            rows.append(dict(question_id=qid, intent=intent, decision=guard["decision"],
                             assessment=trace["assessment_after_selection"]["status"], nfc=is_nfc(question)))
            print("GUARD REPLAY", qid, intent, guard["decision"], "OK", flush=True)
    assert snapshot(retriever) == before
    report = dict(
        status="verified", replays=len(rows),
        blocked_before_retrieval=sum(r["decision"] == "blocked_before_retrieval" for r in rows),
        allowed=sum(r["decision"] == "allowed" for r in rows),
        results_identical_to_original_traces=True, provider_calls=0, database_unchanged=True,
        all_questions_nfc=all(r["nfc"] for r in rows), results=rows,
        note="Cache-only replay of AI-labelled regression questions; not a new quality evaluation.",
    )
    atomic_json(out / "verification.json", report)
    print("AUDIT_DIR=" + str(out))
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
