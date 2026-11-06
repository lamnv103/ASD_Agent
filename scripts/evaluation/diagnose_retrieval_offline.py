"""Offline, read-only retrieval diagnostics from cached query vectors (no provider calls).

Ranks all 33 whole-document vectors for every labelled question and reports, per dataset and
for unique questions, how high the first labelled reference source ranks.

Corrections vs. the first version (2026-11-06 review):
  * retrieval_v1 labels live in reference_labels.json -> labels[*].references (were skipped);
  * results are reported per dataset AND per unique question text (H05 appears in two sets);
  * "hit" = at least one labelled source in top-k; reference lists are not exhaustive, so a
    miss is not proof that every returned source is wrong.
Output: a new folder under reports/verification_runs/ with rankings.json and summary.json.
"""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts/evaluation"))
from audit_output import new_run_dir  # noqa: E402

from rag.retriever import PostgresRetriever, atomic_json  # noqa: E402

DATASETS = ["retrieval_v1", "semantic_reader_v1", "semantic_reader_holdout_v1",
            "reader_v3_development", "reader_v3_holdout", "reader_v3_final_holdout"]


def no_api():
    raise AssertionError("Cache miss: provider access is prohibited in offline diagnostics")


def jsonl(path: Path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]


def load_items():
    items = []
    for name in DATASETS:
        folder = ROOT / "evaluation" / name
        questions = {q["question_id"]: q for q in jsonl(folder / "questions.jsonl")}
        if name == "retrieval_v1":
            labels = json.loads((folder / "reference_labels.json").read_text(encoding="utf-8"))["labels"]
            refs = lambda lab: lab["references"]  # noqa: E731
        else:
            labels = jsonl(folder / "reference_labels.jsonl")
            refs = lambda lab: lab["expected_sources"]  # noqa: E731
        for lab in labels:
            q = questions[lab["question_id"]]
            items.append(dict(dataset=name, question_id=lab["question_id"], query=q.get("query") or q["question"],
                              expected=sorted({r["source_id"] for r in refs(lab)})))
    return items


def metrics(rows):
    best = [min(r["ranks"].values()) for r in rows if r["ranks"]]
    if not best:
        return dict(n=0)
    return dict(n=len(best), **{f"hit@{k}": round(sum(b <= k for b in best) / len(best), 3) for k in (1, 3, 5, 10)},
                mrr=round(sum(1 / b for b in best) / len(best), 3), worst_rank=max(best))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    retriever = PostgresRetriever(key_supplier=no_api)
    retriever.health()
    with retriever._connection() as cur:
        cur.execute("""select d.source_id, e.embedding::text, length(d.content)
            from carobud_rag.documents d join carobud_rag.embeddings e using(collection_id,chunk_id)
            where d.collection_id=%s and e.space_id=%s and d.enabled""",
                    (retriever.config["collection_id"], retriever.config["space_id"]))
        docs = {sid: (json.loads(v), n) for sid, v, n in cur.fetchall()}

    def rank(query):
        vec, usage = retriever.embedder.embed(query)  # validated cache read; raises on miss
        assert usage["cache_hit"]
        nq = math.sqrt(sum(x * x for x in vec))
        scored = sorted((1 - sum(a * b for a, b in zip(vec, dv)) / (nq * math.sqrt(sum(b * b for b in dv))), sid)
                        for sid, (dv, _) in docs.items())
        return [sid for _, sid in scored]

    rows = []
    for item in load_items():
        order = rank(item["query"])
        rows.append(dict(item, ranks={s: order.index(s) + 1 for s in item["expected"]}, top5=order[:5]))

    unique = {}
    for r in rows:
        u = unique.setdefault(r["query"], dict(query=r["query"], datasets=[], ranks={}, top5=r["top5"]))
        u["datasets"].append(f"{r['dataset']}:{r['question_id']}")
        u["ranks"].update(r["ranks"])

    top5_share = Counter(s for u in unique.values() for s in u["top5"])
    summary = dict(
        dataset_rows=len(rows), unique_questions=len(unique),
        by_dataset={d: metrics([r for r in rows if r["dataset"] == d]) for d in DATASETS},
        unique_questions_union_labels=metrics(list(unique.values())),
        misses_beyond_top5=[dict(datasets=u["datasets"], ranks=u["ranks"]) for u in unique.values()
                            if u["ranks"] and min(u["ranks"].values()) > 5],
        top5_frequency_unique_questions={s: c for s, c in top5_share.most_common()},
        never_in_top5=sorted(s for s in docs if top5_share[s] == 0),
        notes=["hit = at least one labelled source in top-k; labels are AI-made and non-exhaustive.",
               "Datasets were used for development; these are regression descriptions, not a benchmark.",
               "Top-5 frequency is descriptive; it does not prove a causal 'hub' effect."],
    )
    out = new_run_dir("retrieval_diagnostics")
    atomic_json(out / "rankings.json", rows)
    atomic_json(out / "summary.json", summary)
    print(json.dumps({k: v for k, v in summary.items() if k != "top5_frequency_unique_questions"}, ensure_ascii=False, indent=2))
    print("AUDIT_DIR=" + str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
