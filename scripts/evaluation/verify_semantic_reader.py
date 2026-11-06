"""Replay accepted semantic pilots against PostgreSQL and cache; no provider API calls."""
from __future__ import annotations
import copy,io,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts/evaluation'))
from rag.retriever import PostgresRetriever,atomic_json,sha
from rag.evidence_pipeline import EvidencePipeline
from rag.semantic_reader import NimEvidenceReader
from evaluate_retriever import snapshot
from audit_output import new_run_dir,assert_protected

def no_api_key():
    raise AssertionError('Audit requires existing caches: an API request would be needed.')

def run():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    work=ROOT/(ROOT/'reports/.semantic_reader_current_run').read_text(encoding='utf-8')
    out_dir=new_run_dir('semantic_reader')
    selection=json.loads((work/'latest_evaluation_runs.json').read_text(encoding='utf-8'))
    r=PostgresRetriever(key_supplier=no_api_key)
    r.health()
    before=json.loads((work/'before.json').read_text(encoding='utf-8'))
    assert snapshot(r)==before,'Database/source baseline changed'
    protected=json.loads((work/'protected_before.json').read_text(encoding='utf-8'))
    assert_protected(protected)
    pipe=EvidencePipeline(r)
    pipe.semantic_reader=NimEvidenceReader(counter=pipe.counter,key_supplier=no_api_key)
    results=[];reviewed_spans=0;passage_count=0;token_deltas=[];source_cache={}
    for name in selection['runs']:
        folder=(ROOT/name).resolve()
        assert folder.is_relative_to(work.resolve()),'Run outside current work folder'
        summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
        frozen=json.loads((folder/'frozen_inputs.json').read_text(encoding='utf-8'))
        assert all(sha((folder/n).read_bytes())==h for n,h in frozen['files'].items())
        for row in summary['results']:
            assert row['status']=='ok','Latest selection contains a failed question'
            original=json.loads((folder/'traces'/(row['question_id']+'.json')).read_text(encoding='utf-8'))
            # This is real PostgreSQL retrieval, never a synthetic/source-file fallback.
            retrieved=r.retrieve(row['question'],5,include_content=True)
            assert retrieved['query_embedding']['cache_hit'] is True
            assert [{k:v for k,v in d.items() if k!='content'} for d in retrieved['results']]==original['retrieval']['sources']
            source_cache.update({d['source_id']:d for d in retrieved['results']})
            trace=pipe.prepare_retrieved(row['question'],retrieved)
            for key in ['assessment_before_selection','assessment_after_selection']:
                for field in ['status','claims','conflicts','missing_claims','used_evidence_ids']:
                    assert trace[key][field]==original[key][field],(row['question_id'],key,field)
            assert trace['medical_policy_after_selection']==original['medical_policy_after_selection']
            assert trace['context_selection']==original['context_selection']
            assert trace['generation_enabled'] is False and trace['evaluation_reference_mode'] is False
            assert trace['context_selection']['budget']['within_budget'] is True
            model=trace['semantic_reader']
            assert model['provider']['cache_hit'] is True
            token_deltas.append(model['provider']['prompt_token_delta'])
            if model.get('verification'):
                assert model['verification']['provider']['cache_hit'] is True
                token_deltas.append(model['verification']['provider']['prompt_token_delta'])
            for ex in model['excerpts']:
                d=source_cache[ex['source_id']]
                assert ex['content_sha256']==d['content_sha256']
                for p in ex['passages']:
                    assert 0<=ex['start']<=p['start']<p['end']<=ex['end']<=len(d['content'])
                    assert d['content'][p['start']:p['end']]==p['text']
                    passage_count+=1
            for item in model['review']['items']:
                d=source_cache[item['source_id']]
                assert d['content'][item['start']:item['end']]==item['quote']
                for scope in json.loads(item['scope_limits']):
                    assert source_cache[scope['source_id']]['content'][scope['start']:scope['end']]==scope['quote']
                reviewed_spans+=1
            if model['review']['intent'] in {'individual_diagnosis','personalized_medication','scope_legal','current_services'}:
                assert trace['context_selection']['selected_blocks']==[]
                assert trace['assessment_after_selection']['status']=='insufficient'
            results.append(dict(question_id=row['question_id'],assessment=row['assessment'],provisional_label_agreement=row['status_matches_provisional_reference'],trace_sha256=sha((folder/'traces'/(row['question_id']+'.json')).read_bytes())))
            print('AUDIT',row['question_id'],'cache-only replay/positions/budget verified',flush=True)
    after=snapshot(r)
    assert after==before
    assert_protected(protected)
    regression=json.loads((work/'retrieval_regression.json').read_text(encoding='utf-8'))
    assert regression['questions']==30 and regression['ranks_and_distances_identical'] is True
    out=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(stream=out,verbosity=2).run(suite)
    (out_dir/'final_tests.txt').write_text(out.getvalue(),encoding='utf-8')
    assert result.wasSuccessful(),out.getvalue()
    atomic_json(out_dir/'after.json',after)
    report=dict(status='technical_verification_passed_semantic_review_pending',recorded_at=datetime.now(timezone(timedelta(hours=7))).isoformat(),
        current_collection=r.config['collection_id'],current_space=r.config['space_id'],documents=33,vectors=33,
        accepted_pilot_questions=len(results),cache_only_replays=len(results),api_calls_during_audit=0,
        original_passages_checked=passage_count,reviewed_item_spans_checked=reviewed_spans,
        context_and_policy_replays_identical=True,database_snapshot_unchanged=True,source_library_files_unchanged=132,
        protected_configuration_and_retriever_files_unchanged=len(protected),old_retrieval_queries_unchanged=30,
        observed_prompt_token_deltas=sorted(set(token_deltas)),usage_counts_match_on_observed_requests=bool(token_deltas) and all(d==0 for d in token_deltas),
        tests_run=result.testsRun,tests_failed=len(result.failures),tests_errors=len(result.errors),tests_skipped=len(result.skipped),
        provisional_label_agreement_count=sum(x['provisional_label_agreement'] is True for x in results),
        provisional_disagreements=[x['question_id'] for x in results if not x['provisional_label_agreement']],
        reference_labels_are_ai_reviewed_not_clinically_adjudicated=True,semantic_accuracy_established=False,
        independent_clinical_validation=False,patient_answer_generation_enabled=False,
        runs=selection['runs'],results=results)
    atomic_json(out_dir/'verification.json',report);print('AUDIT_DIR='+str(out_dir),flush=True)
    print(json.dumps({k:v for k,v in report.items() if k not in {'results','runs'}},ensure_ascii=False,indent=2))
    return 0
if __name__=='__main__':sys.exit(run())
