"""Read-only/cache-only audit of v3 plus unchanged v2 and retriever behavior."""
from __future__ import annotations
import io,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts/evaluation'))
from rag.retriever import PostgresRetriever,sha,atomic_json
from rag.evidence_pipeline import EvidencePipeline
from rag.semantic_reader import NimEvidenceReader
from rag.semantic_reader_v3 import AtomicNeedsReader
from evaluate_retriever import snapshot
from audit_output import new_run_dir

def no_api():raise AssertionError('Audit cache miss: API calls are prohibited.')
def stable_comparison(new,old):
    for section in ['assessment_before_selection','assessment_after_selection']:
        for field in ['status','claims','conflicts','missing_claims','used_evidence_ids']:
            assert new[section][field]==old[section][field],(section,field)
    assert new['context_selection']==old['context_selection']
    assert new['medical_policy_after_selection']==old['medical_policy_after_selection']

def run():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    work=ROOT/(ROOT/'reports/.reader_refinement_current_run').read_text(encoding='utf-8')
    out=new_run_dir('reader_v3')
    selection=json.loads((work/'evaluation_selection.json').read_text(encoding='utf-8'))
    r=PostgresRetriever(key_supplier=no_api);r.health()
    baseline=json.loads((work/'before.json').read_text(encoding='utf-8'));assert snapshot(r)==baseline
    protected=json.loads((work/'protected_before.json').read_text(encoding='utf-8'))
    assert all(sha((ROOT/p).read_bytes())==h for p,h in protected.items())
    pipe=EvidencePipeline(r);pipe.semantic_reader=AtomicNeedsReader(counter=pipe.counter,key_supplier=no_api)
    results=[];span_count=0;prompt_deltas=[]
    for name in selection['runs']:
        folder=ROOT/name;summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
        assert summary['status']=='complete','Do not present partial/error runs as complete audit inputs'
        frozen=json.loads((folder/'frozen_inputs.json').read_text(encoding='utf-8'))
        assert all(sha((folder/n).read_bytes())==h for n,h in frozen['files'].items())
        implementation=json.loads((folder/'implementation.json').read_text(encoding='utf-8'))
        assert all(sha((ROOT/n).read_bytes())==h for n,h in implementation['files'].items()),'Evaluation used another implementation'
        for row in summary['results']:
            q=row['question_id'];original=json.loads((folder/'traces'/(q+'.json')).read_text(encoding='utf-8'))
            retrieval=r.retrieve(row['question'],5,include_content=True);assert retrieval['query_embedding']['cache_hit']
            assert [{k:v for k,v in d.items() if k!='content'} for d in retrieval['results']]==original['retrieval']['sources']
            docs={d['source_id']:d for d in retrieval['results']}
            trace=pipe.prepare_retrieved(row['question'],retrieval);stable_comparison(trace,original)
            assert trace['generation_enabled'] is False and trace['evaluation_reference_mode'] is False
            assert trace['context_selection']['budget']['within_budget'] is True
            sr=trace['semantic_reader']
            for c in sr['calls']:
                assert c['cache_hit'];prompt_deltas.append(c['prompt_token_delta'])
            for x in sr['excerpts']:
                assert 'metadata' not in x,'Curator metadata entered semantic reading payload'
                d=docs[x['source_id']];assert d['content_sha256']==x['content_sha256']
                for p in x['passages']:
                    assert 0<=x['start']<=p['start']<p['end']<=x['end']<=len(d['content'])
                    assert d['content'][p['start']:p['end']]==p['text']
            for item in sr['review']['items']:
                d=docs[item['source_id']];assert d['content'][item['start']:item['end']]==item['quote'];span_count+=1
                need=item['need_judgment']['need'];assert need['need_id'] in item['claim_ids']
                assert need==next(n for n in sr['plan']['needs'] if n['need_id']==need['need_id'])
                judgment=item['need_judgment'];decision=judgment['verification']
                packet=next(p for p in sr['verification_packets'] if p['item_id']==decision['item_id'])
                assert set(decision['support_passage_ids'])<=set(packet['allowed_passage_ids'])
                for proof in judgment['supporting_passages']+judgment['source_scope_passages']:
                    source=docs[proof['source_id']]
                    assert source['content'][proof['start']:proof['end']]==proof['quote']
                for part in item.get('additional_source_passages',[]):
                    assert docs[part['source_id']]['content'][part['start']:part['end']]==part['text']
                if item['relation']!='topical':
                    assert judgment['supporting_passages'],'Evidence lacks original proof passages'

            if sr['review']['intent'] in {'individual_diagnosis','personalized_medication','scope_legal','current_services'}:
                assert trace['context_selection']['selected_blocks']==[]
                assert trace['assessment_after_selection']['status']=='insufficient'
                assert 1<=len(sr['calls'])<=2 and all(c['stage'] in {'question_plan','question_plan_repair'} for c in sr['calls'])
            results.append(dict(question_id=q,assessment=row['assessment'],provisional_agreement=row['reference_status_agreement'],trace_sha256=sha((folder/'traces'/(q+'.json')).read_bytes())))
            print('V3 AUDIT',q,'verified',flush=True)
    # Compare v2 behavior against original traces, writing only this new report.
    oldwork=ROOT/'reports/semantic_reader_20261101_111654'
    legacy=json.loads((oldwork/'latest_evaluation_runs.json').read_text(encoding='utf-8'))['runs']
    oldpipe=EvidencePipeline(r);legacy_count=0
    for name in legacy:
        folder=ROOT/name
        oldcfg=json.loads((folder/'model_and_reader_config.json').read_text(encoding='utf-8'))['reader']
        oldpipe.semantic_reader=NimEvidenceReader(oldcfg,counter=oldpipe.counter,key_supplier=no_api)
        for row in json.loads((folder/'summary.json').read_text(encoding='utf-8'))['results']:
            original=json.loads((folder/'traces'/(row['question_id']+'.json')).read_text(encoding='utf-8'))
            trace=oldpipe.prepare(row['question']);stable_comparison(trace,original);legacy_count+=1
    # Original 30 rankings/distances, independent of any semantic model.
    raw=ROOT/'reports/retrieval_evaluation/R33_20261031_124523_966748/raw_results.jsonl'
    old_results=[json.loads(s) for s in raw.read_text(encoding='utf-8').splitlines()]
    old_queries=[json.loads(s) for s in (ROOT/'evaluation/retrieval_v1/questions.jsonl').read_text(encoding='utf-8').splitlines()]
    ranking_count=0
    for q,stored in zip(old_queries,old_results):
        assert stored['question_id']==q['question_id']
        expected=stored.get('result',stored)
        new=r.retrieve(q['query'],5,include_content=False)
        assert [(d['source_id'],d['cosine_distance']) for d in new['results']]==[(d['source_id'],d['cosine_distance']) for d in expected['results']]
        assert new['query_embedding']['cache_hit'];ranking_count+=1
    assert ranking_count==30 and legacy_count==20
    assert snapshot(r)==baseline
    assert all(sha((ROOT/p).read_bytes())==h for p,h in protected.items())
    stream=io.StringIO();suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    tests=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (out/'final_tests.txt').write_text(stream.getvalue(),encoding='utf-8');assert tests.wasSuccessful(),stream.getvalue()
    report=dict(status='technical_passed_semantic_results_require_adjudication',recorded_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
        documents=33,vectors=33,source_files_unchanged=132,database_unchanged=True,
        v3_cached_replays=len(results),v2_replays_identical=legacy_count,original_rankings_identical=ranking_count,
        validated_item_spans=span_count,prompt_token_deltas=sorted(set(prompt_deltas)),api_calls_during_audit=0,
        tests=tests.testsRun,tests_failed=len(tests.failures),tests_errors=len(tests.errors),tests_skipped=len(tests.skipped),
        patient_generation_enabled=False,independent_clinical_validation=False,semantic_accuracy_established=False,results=results)
    atomic_json(out/'verification.json',report);atomic_json(out/'after.json',baseline);print('AUDIT_DIR='+str(out),flush=True)
    print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False,indent=2))
    return 0
if __name__=='__main__':sys.exit(run())
