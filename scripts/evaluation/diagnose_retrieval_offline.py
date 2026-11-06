"""Offline, read-only retrieval diagnostics using cached query vectors (no API calls)."""
import json, glob, sys, collections, statistics as st
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(r"D:\AI4LIFE\ASD_AGENT"); sys.path.insert(0, str(ROOT))
from rag.retriever import PostgresRetriever

r = PostgresRetriever()
with r._connection() as cur:
    cur.execute("""select d.source_id, e.embedding::text, length(d.content) from carobud_rag.documents d
        join carobud_rag.embeddings e using(collection_id,chunk_id)
        where d.collection_id=%s and e.space_id=%s and d.enabled""", (r.config["collection_id"], r.config["space_id"]))
    docs = {sid: (json.loads(v), n) for sid, v, n in cur.fetchall()}
print("docs", len(docs))

def cos(a, b):
    import math
    return sum(x*y for x, y in zip(a, b)) / (math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(y*y for y in b)))

cache = {}
for f in glob.glob(str(ROOT/"reports/retriever/query_cache/*.json")):
    d = json.loads(Path(f).read_text(encoding="utf-8")); cache[d["identity"]["query"]] = d["embedding"]

# Collect (set, qid, question, expected source ids)
items = []
def load_jsonl(p): return [json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]
for setname in ["reader_v3_development", "reader_v3_holdout", "reader_v3_final_holdout", "semantic_reader_v1", "semantic_reader_holdout_v1"]:
    qs = {q["question_id"]: q for q in load_jsonl(ROOT/f"evaluation/{setname}/questions.jsonl")}
    for lab in load_jsonl(ROOT/f"evaluation/{setname}/reference_labels.jsonl"):
        exp = sorted({e["source_id"] for e in lab.get("expected_sources", [])})
        q = qs.get(lab["question_id"])
        if q: items.append((setname, lab["question_id"], q.get("query", q["question"]), exp))
rl = json.loads((ROOT/"evaluation/retrieval_v1/reference_labels.json").read_text(encoding="utf-8"))
qs = {q["question_id"]: q for q in load_jsonl(ROOT/"evaluation/retrieval_v1/questions.jsonl")}
labs = rl if isinstance(rl, list) else rl.get("labels", rl.get("questions", []))
if isinstance(labs, dict): labs = [dict(question_id=k, **v) for k, v in labs.items()]
for lab in labs:
    srcs = lab.get("expected_sources") or lab.get("sources") or lab.get("candidates") or []
    exp = sorted({(s["source_id"] if isinstance(s, dict) else s) for s in srcs})
    q = qs.get(lab["question_id"])
    if q: items.append(("retrieval_v1", lab["question_id"], q["query"], exp))

seen = set(); rows = []; top5_counter = collections.Counter(); gaps = []; spreads = []
for setname, qid, query, exp in items:
    key = (setname, qid)
    if key in seen: continue
    seen.add(key)
    vec = cache.get(query)
    if vec is None: rows.append((setname, qid, "NO_CACHE", exp, None)); continue
    ranked = sorted(((1 - cos(vec, dv), sid) for sid, (dv, _) in docs.items()))
    order = [s for _, s in ranked]
    for s in order[:5]: top5_counter[s] += 1
    dists = [d for d, _ in ranked]
    gaps.append(dists[4] - dists[0]); spreads.append(dists[-1] - dists[0])
    ranks = {e: order.index(e) + 1 for e in exp if e in order}
    rows.append((setname, qid, query[:70], ranks, round(dists[4]-dists[0], 4)))

print("\nquestions analysed:", len(rows), " with cached vector:", sum(1 for r_ in rows if r_[2] != "NO_CACHE"))
with_exp = [r_ for r_ in rows if r_[2] != "NO_CACHE" and r_[3]]
best = [min(r_[3].values()) for r_ in with_exp]
print("questions with expected sources:", len(with_exp))
for k in (1, 3, 5, 10):
    print(f"hit@{k}: {sum(b <= k for b in best)}/{len(best)} = {sum(b <= k for b in best)/len(best):.3f}")
print("MRR (full ranking):", round(sum(1/b for b in best)/len(best), 3))
print("median best rank:", st.median(best), " worst:", max(best))
print("\ndistance gap rank1->rank5: median", round(st.median(gaps), 4), "min", round(min(gaps), 4), "max", round(max(gaps), 4))
print("distance spread rank1->rank33: median", round(st.median(spreads), 4))
print("\nby set:")
for s in sorted({r_[0] for r_ in with_exp}):
    b = [min(r_[3].values()) for r_ in with_exp if r_[0] == s]
    print(f"  {s:28s} n={len(b):2d} hit@1={sum(x<=1 for x in b)/len(b):.2f} hit@5={sum(x<=5 for x in b)/len(b):.2f} MRR={sum(1/x for x in b)/len(b):.3f}")
print("\nmisses beyond top5:")
for r_ in with_exp:
    if min(r_[3].values()) > 5: print("  ", r_[0], r_[1], r_[3], r_[2])
n = sum(1 for r_ in rows if r_[2] != "NO_CACHE")
print(f"\nhubness: share of {n} queries where doc is in top5")
for sid, c in top5_counter.most_common(8): print(f"  {sid:32s} {c:3d}  {c/n:.0%}  len={docs[sid][1]}")
never = [s for s in docs if top5_counter[s] == 0]
print("docs never in any top5:", len(never), never)
lens = [(docs[s][1], top5_counter[s]) for s in docs]
import math
mx = st.mean(l for l, _ in lens); my = st.mean(c for _, c in lens)
cov = sum((l-mx)*(c-my) for l, c in lens); vx = math.sqrt(sum((l-mx)**2 for l, _ in lens)); vy = math.sqrt(sum((c-my)**2 for _, c in lens))
print("corr(doc length, top5 frequency):", round(cov/(vx*vy), 3))
