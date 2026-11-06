"""Independent cache-only audit; writes only to a new audit directory.

Run from the project root with .venv-embedding/Scripts/python.exe -B
reports/review_20261106/audit_project.py. No provider requests are allowed.
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
import csv
import hashlib
import json
import math
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts/evaluation'))
from rag.retriever import PostgresRetriever
from rag.evidence_pipeline import EvidencePipeline
from rag.semantic_reader_v3 import AtomicNeedsReader
from verify_reader_v3 import stable_comparison
from evaluate_retriever import snapshot


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def lines(path):
    return [json.loads(s) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]


def no_api():
    raise AssertionError('Cache miss: provider access is prohibited during this audit')


def metrics(rows):
    eligible = [r for r in rows if r['ranks']]
    best = [min(r['ranks'].values()) for r in eligible]
    return dict(n=len(best), **{f'hit@{k}': sum(b <= k for b in best) / len(best)
                for k in (1, 3, 5, 10)}, mrr=sum(1 / b for b in best) / len(best))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    out = Path(__file__).parent / ('audit_' + datetime.now(timezone(timedelta(hours=7))).strftime('%Y%m%d_%H%M%S_%f'))
    out.mkdir()
    report = dict(recorded_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
                  provider_calls=0, limitations=['Cached replay is not a new model evaluation or a production benchmark.'])
    retriever = PostgresRetriever(key_supplier=no_api)
    report['health'] = retriever.health()
    before = snapshot(retriever)
    with retriever._connection() as cur:
        cur.execute('''select d.source_id, e.embedding::text, length(d.content)
          from carobud_rag.documents d join carobud_rag.embeddings e using(collection_id,chunk_id)
          where d.collection_id=%s and e.space_id=%s and d.enabled''',
          (retriever.config['collection_id'], retriever.config['space_id']))
        docs = {sid: (json.loads(v), n) for sid, v, n in cur.fetchall()}
    items = []
    for name in ('reader_v3_development', 'reader_v3_holdout', 'reader_v3_final_holdout',
                 'semantic_reader_v1', 'semantic_reader_holdout_v1', 'retrieval_v1'):
        folder = ROOT / 'evaluation' / name
        qs = {q['question_id']: q for q in lines(folder / 'questions.jsonl')}
        labels = read(folder / 'reference_labels.json')['labels'] if name == 'retrieval_v1' else lines(folder / 'reference_labels.jsonl')
        for label in labels:
            q = qs[label['question_id']]
            query = q.get('query') or q.get('question')
            refs = label['references'] if name == 'retrieval_v1' else label['expected_sources']
            items.append(dict(dataset=name, question_id=q['question_id'], query=query,
                              expected=sorted({r['source_id'] for r in refs})))
    ranked_rows = []
    for item in items:
        # Use the retriever's checked cache reader, not just the raw cached vector.
        vec, usage = retriever.embedder.embed(item['query'])
        assert usage['cache_hit']
        norm = math.sqrt(sum(x*x for x in vec))
        ranking = sorted((1 - sum(a*b for a, b in zip(vec, dv)) /
                          (norm * math.sqrt(sum(x*x for x in dv))), sid)
                         for sid, (dv, _) in docs.items())
        order = [sid for _, sid in ranking]
        assert all(s in order for s in item['expected'])
        ranked_rows.append(dict(**item, ranks={s: order.index(s)+1 for s in item['expected']}, top5=order[:5]))
    by_query = {}
    for row in ranked_rows:
        if row['query'] not in by_query:
            by_query[row['query']] = dict(row, ranks=dict(row['ranks']))
        else:
            by_query[row['query']]['ranks'].update(row['ranks'])
    report['retrieval'] = dict(
        dataset_rows=len(ranked_rows), unique_queries=len(by_query),
        reader_rows=metrics([r for r in ranked_rows if r['dataset'] != 'retrieval_v1']),
        all_rows=metrics(ranked_rows), unique_queries_union_references=metrics(list(by_query.values())),
        by_dataset={name: metrics([r for r in ranked_rows if r['dataset'] == name])
                    for name in sorted({r['dataset'] for r in ranked_rows})},
        misses=[r for r in ranked_rows if r['ranks'] and min(r['ranks'].values()) > 5],
        note='Hit means at least one reference source; reference lists are non-exhaustive. Union labels only for descriptive deduplication.')
    (out / 'rankings.json').write_text(json.dumps(ranked_rows, ensure_ascii=False, indent=2), encoding='utf-8')

    work = ROOT / (ROOT / 'reports/.reader_refinement_current_run').read_text(encoding='utf-8').strip()
    protected = read(work / 'protected_before.json')
    assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in protected.items())
    pipe = EvidencePipeline(retriever)
    pipe.semantic_reader = AtomicNeedsReader(counter=pipe.counter, key_supplier=no_api)
    rows = []
    for name in read(work / 'evaluation_selection.json')['runs']:
        folder = ROOT / name
        assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
                   for p, h in read(folder / 'implementation.json')['files'].items())
        for row in read(folder / 'summary.json')['results']:
            original = read(folder / 'traces' / (row['question_id'] + '.json'))
            trace = pipe.prepare(row['question'])
            stable_comparison(trace, original)
            calls = trace['semantic_reader']['calls']
            assert all(c['cache_hit'] for c in calls)
            assert trace['generation_enabled'] is False
            assert trace['context_selection']['budget']['within_budget']
            rows.append({k: row[k] for k in ('question_id', 'assessment', 'reference_status_agreement',
                         'reference_span_overlap_used', 'expected_source_in_top5')})
            print('Replay', row['question_id'], 'OK', flush=True)
    report['v3_replay'] = dict(n=len(rows), provisional_agreement=sum(r['reference_status_agreement'] for r in rows),
                               results=rows, all_calls_cached=True)
    histories = []
    for path in sorted(work.glob('run_*/summary.json')):
        summary = read(path)
        for row in summary['results']:
            histories.append(dict(run=path.parent.name, **row))
    report['development_history'] = dict(
        runs=len(list(work.glob('run_*/summary.json'))), attempts=len(histories),
        errors=dict(Counter(r.get('error_code') for r in histories if r['status'] != 'ok')),
        note='Mixed development versions, repeated questions, cached and live calls; not an estimate of serving reliability.')
    timings = {}
    for row in histories:
        for call in row.get('model_calls', []):
            timings[call['request_id']] = call
    durations = [c['elapsed_seconds'] for c in timings.values()]
    report['historical_stage_timings'] = dict(n_unique_requests=len(durations),
        median=statistics.median(durations), maximum=max(durations),
        note='Original per-request elapsed_seconds retained in cached telemetry; not end-to-end latency.')
    totals = []
    for name in read(work / 'evaluation_selection.json')['runs']:
        for row in read(ROOT / name / 'summary.json')['results']:
            calls = row['model_calls']
            totals.append(dict(question_id=row['question_id'], calls=len(calls),
                sum_original_stage_seconds=round(sum(c['elapsed_seconds'] for c in calls), 3),
                input_tokens=sum(c['usage'].get('prompt_tokens', 0) for c in calls)))
    report['selected_historical_request_costs'] = totals
    with (ROOT / 'knowledge/rag/source_library/CLINICAL_REVIEW_QUEUE.csv').open(encoding='utf-8-sig', newline='') as f:
        queue = list(csv.DictReader(f))
    report['clinical_queue'] = dict(n=len(queue), named_reviewers=sum(bool(r['independent_clinician_name'].strip()) for r in queue),
                                    decisions=sum(bool(r['clinical_decision'].strip()) for r in queue))
    report['database_snapshot_unchanged'] = snapshot(retriever) == before
    report['protected_files_unchanged'] = all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in protected.items())
    assert report['database_snapshot_unchanged'] and report['protected_files_unchanged']
    (out / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('AUDIT_DIR=' + str(out))
    print(json.dumps({k: v for k, v in report.items() if k not in ('v3_replay', 'selected_historical_request_costs', 'retrieval')}, ensure_ascii=False, indent=2))
    print(json.dumps(report['retrieval']['by_dataset'], ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
