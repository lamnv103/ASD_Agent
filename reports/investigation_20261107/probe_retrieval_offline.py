"""Offline probe for the H05/N02 retrieval misses (no provider calls, no DB writes).

Exploratory diagnostic for reports/investigation_20261107/DIEU_TRA_4_CA.md. Not an evaluation:
the 18 labelled reader-v3 questions were used during development, labels are AI-made and
not exhaustive. Reads only files already in the repo:
  - 33 whole-document vectors (reports/whole_document_embedding_20261030/...jsonl)
  - 67 cached query vectors (reports/retriever/query_cache/*.json)
  - documents.json, reader-v3 traces and reference labels.
Writes probe_output.json and probe_output.txt next to this script.

Usage:  python reports/investigation_20261107/probe_retrieval_offline.py
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NIMH = "NIH-NIMH-ASD-2025"
RUNS = ROOT / "reports/reader_refinement_20261101_232742"
STOP = set("the of and or in to a for with is are on as by be at an that this from it its not no can".split())
SOURCE_NAMES = re.compile(r"\b(nimh|nidcd|cdc|nih|aap|asha|pmc\d+)\b", re.I)
VIETNAM = re.compile(r"\b(Viet ?Nam|Vietnam(ese)?|Hanoi|Ha Noi)\b", re.I)


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


def load():
    docs = [json.loads(s) for s in (ROOT / "reports/whole_document_embedding_20261030/whole_document_embeddings.jsonl")
            .read_text(encoding="utf-8").splitlines() if s.strip()]
    queries = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "reports/retriever/query_cache").glob("*.json"))]
    body = {x["id"]: x["noi_dung"] for x in json.loads((ROOT / "knowledge/rag/source_library/documents.json")
                                                        .read_text(encoding="utf-8"))["tai_lieu"]}
    results = json.loads((RUNS / "results_latest_23.json").read_text(encoding="utf-8"))
    labels = {}
    for name in ["reader_v3_development", "reader_v3_holdout", "reader_v3_final_holdout"]:
        for line in (ROOT / "evaluation" / name / "reference_labels.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                labels[d["question_id"]] = sorted({s["source_id"] for s in d.get("expected_sources", [])})
    return docs, queries, body, results, labels


def dense_analysis(docs, queries, body, out, lines):
    size = {d["source_id"]: d["input_characters"] for d in docs}
    top5 = Counter()
    ranking = {}
    nimh_rank = {}
    for q in queries:
        scored = sorted(((cos(q["embedding"], d["embedding"]), d["source_id"]) for d in docs), reverse=True)
        text = q["identity"]["query"]
        ranking[text] = [(round(v, 4), s) for v, s in scored]
        nimh_rank[text] = [s for _, s in scored].index(NIMH) + 1
        top5.update(s for _, s in scored[:5])
    slots = 5 * len(queries)
    lines.append(f"Cached queries: {len(queries)}; top-5 slots: {slots}; mean slots per document: {slots / len(docs):.1f}")
    lines.append("Top-5 frequency | source | body chars | mentions of Viet Nam")
    freq_rows = []
    for s in sorted(size, key=lambda s: -top5[s]):
        vn = len(VIETNAM.findall(body[s]))
        freq_rows.append(dict(source_id=s, top5_count=top5[s], body_chars=size[s], vietnam_mentions=vn))
        lines.append(f"  {top5[s]:3d}  {s:34s} {size[s]:7d}  {vn:4d}")
    out["top5_frequency"] = freq_rows
    out["documents_truncated"] = [d["source_id"] for d in docs if d["sent_characters"] != d["input_characters"] or d["truncate"] != "NONE"]
    lines.append(f"Documents truncated at embedding time: {out['documents_truncated'] or 'none'}")
    out["dense_rankings"] = {}
    for key, qid in [("nhất thiết có biểu hiện", "H05"), ("giọng điệu, nét mặt", "N02"), ("Vì sao gọi tự kỷ là phổ", "paraphrase_H05")]:
        text = next(t for t in ranking if key in t)
        r = ranking[text]
        without_vn = [s for _, s in r if s not in ("ASD-OA-PMC13005892", "ASD-OA-PMC6487529")]
        out["dense_rankings"][qid] = dict(query=text, nimh_rank=nimh_rank[text],
                                          nimh_rank_without_two_vietnam_papers=without_vn.index(NIMH) + 1,
                                          top22=r[:22])
        lines.append(f"\n[{qid}] {text}")
        lines.append(f"  NIMH rank {nimh_rank[text]}; without the two Viet Nam papers: {without_vn.index(NIMH) + 1}")
        for i, (v, s) in enumerate(r[:6], 1):
            lines.append(f"  {i:2d} {v:.4f} {s}")
        lines.append(f"  score spread rank1-rank20: {r[0][0] - r[19][0]:.4f}")


def sections(text):
    parts = [p for p in re.split(r"(?m)^(?=#{1,6} )", text) if len(p) > 200]
    return parts or [text]


def tokens(s):
    return [w for w in re.findall(r"[a-z][a-z\-]+", s.lower()) if w not in STOP]


def bm25(units):
    toks = [tokens(u) for _, u in units]
    n, avg = len(toks), sum(map(len, toks)) / len(toks)
    df = Counter(w for t in toks for w in set(t))
    tfs = [Counter(t) for t in toks]

    def score(query):
        q = tokens(query)
        out = []
        for i, (tf, t) in enumerate(zip(tfs, toks)):
            s = sum(math.log(1 + (n - df[w] + .5) / (df[w] + .5)) * tf[w] * 2.2 / (tf[w] + 1.2 * (.25 + .75 * len(t) / avg))
                    for w in q if w in tf)
            out.append((s, i))
        return sorted(out, reverse=True)
    return score


def lexical_analysis(body, results, labels, out, lines):
    doc_units = list(body.items())
    sec_units = [(sid, s) for sid, text in body.items() for s in sections(text)]
    doc_score, sec_score = bm25(doc_units), bm25(sec_units)
    rows = []
    for r in results:
        exp = set(labels.get(r["question_id"]) or [])
        if not exp:
            continue
        trace = json.loads((ROOT / r["run"] / "traces" / f"{r['question_id']}.json").read_text(encoding="utf-8"))
        terms = [t for need in trace["semantic_reader"]["plan"]["needs"] for t in need["search_terms"]]
        q = " ".join(terms)
        doc_top = [doc_units[i][0] for _, i in doc_score(q)[:5]]
        sec_rank, seen = [], set()
        sec_hits = sec_score(q)
        for _, i in sec_hits:
            sid = sec_units[i][0]
            if sid not in seen:
                seen.add(sid)
                sec_rank.append(sid)
        row = dict(question_id=r["question_id"], expected=sorted(exp),
                   terms_name_a_source=any(SOURCE_NAMES.search(t) for t in terms),
                   dense_top5_hit=bool(exp & set(r["top5_sources"])),
                   bm25_doc_top5_hit=bool(exp & set(doc_top)),
                   bm25_section_top5_hit=bool(exp & set(sec_rank[:5])),
                   bm25_section_best_rank=min(sec_rank.index(e) + 1 for e in exp),
                   top_sections=[dict(source_id=sec_units[i][0], score=round(s, 2), heading=sec_units[i][1].splitlines()[0][:90])
                                 for s, i in sec_hits[:4]])
        rows.append(row)
    out["lexical_probe"] = rows
    clean = [x for x in rows if not x["terms_name_a_source"]]
    lines.append("\nLexical probe (BM25 on reader-plan English search_terms; exploratory)")
    for x in rows:
        lines.append(f"  {x['question_id']:4s} dense={'Y' if x['dense_top5_hit'] else 'N'} bm25doc={'Y' if x['bm25_doc_top5_hit'] else 'N'} "
                     f"bm25sec={'Y' if x['bm25_section_top5_hit'] else 'N'} best_sec_rank={x['bm25_section_best_rank']}"
                     f"{'  [terms name a source]' if x['terms_name_a_source'] else ''}")
    for label, subset in [("all", rows), ("terms without source names", clean)]:
        lines.append(f"  {label}: n={len(subset)} dense={sum(x['dense_top5_hit'] for x in subset)} "
                     f"bm25doc={sum(x['bm25_doc_top5_hit'] for x in subset)} bm25sec={sum(x['bm25_section_top5_hit'] for x in subset)}")
    for qid in ("H05", "N02"):
        x = next(r for r in rows if r["question_id"] == qid)
        lines.append(f"  [{qid}] top sections:")
        for t in x["top_sections"]:
            lines.append(f"     {t['score']:6.2f} {t['source_id']} :: {t['heading']}")


def main():
    docs, queries, body, results, labels = load()
    out, lines = {"note": __doc__.strip().splitlines()[0]}, []
    dense_analysis(docs, queries, body, out, lines)
    lexical_analysis(body, results, labels, out, lines)
    (HERE / "probe_output.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "probe_output.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
