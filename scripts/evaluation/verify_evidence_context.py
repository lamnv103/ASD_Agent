"""Integration/replay checks; reference reviews are not an autonomous-reader benchmark."""
from pathlib import Path
import copy,json,sys,collections,io,unittest,importlib.metadata
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts/evaluation'))
from rag.retriever import PostgresRetriever,atomic_json,sha,canonical
from rag.evidence_pipeline import EvidencePipeline
from evaluate_retriever import snapshot,load_inputs
from audit_output import new_run_dir,assert_frozen_json

def main():
    run=ROOT/(ROOT/'reports/.evidence_context_current_run').read_text(encoding='utf-8')
    r=PostgresRetriever();before=json.loads((run/'before.json').read_text(encoding='utf-8'));assert snapshot(r)==before
    protected=json.loads((run/'protected_code_before.json').read_text(encoding='utf-8'))
    assert all(sha((ROOT/n).read_bytes())==v for n,v in protected.items())
    questions,labels,frozen=load_inputs(r)
    baseline=ROOT/'reports/retrieval_evaluation/R33_20261031_124523_966748'
    old={x['question_id']:x['result'] for x in map(json.loads,(baseline/'raw_results.jsonl').read_text(encoding='utf-8').splitlines())}
    inputs=ROOT/'evaluation/evidence_context_v1';inputs.mkdir(exist_ok=True)
    out=new_run_dir('evidence_context');traces=out/'traces';traces.mkdir()
    pipeline=EvidencePipeline(r);reviews=[];results=[];saved={}
    with patch.object(r.embedder,'_key',side_effect=AssertionError('Integration replay must not call API')):
        for q in questions:
            qid=q['question_id'];lab=labels[qid];is_partial=any(e['support'] in {'MOT_PHAN','GIOI_HAN'} for e in lab['references'])
            review=dict(schema_version=1,review_id='reference-replay-'+qid,question=q['question'],question_sha256=sha(q['question']),
                reviewer=dict(kind='ai_reference_review',name=lab['reviewer'],date=lab['review_date']),
                provenance=dict(origin='existing_retrieval_v1_label_replay_not_independent_semantic_evaluation',frozen_input_hashes=frozen['files']),
                intent={'Q27':'scope_legal','Q28':'individual_diagnosis','Q29':'personalized_medication','Q30':'current_services'}.get(qid,'general_information'),
                claims=[dict(claim_id='c1',text=q['question'] if not is_partial else 'Phần được nguồn hỗ trợ theo nhãn tham chiếu hiện có',required=True)],items=[],conflicts=[],review_notes=lab['expected_behavior'])
            if is_partial:review['claims'].append(dict(claim_id='c2',text='Phần chưa đủ căn cứ theo nhãn hiện có: '+lab['expected_behavior'],required=True))
            for i,e in enumerate(lab['references']):
                review['items'].append(dict(item_id='item-'+str(i),source_id=e['source_id'],content_sha256=e['content_sha256'],start=e['start'],end=e['end'],quote=e['quote'],
                    relation='direct',stance='supports',claim_ids=['c1'],scope_limits=e['scope_limits']))
            assert_frozen_json(inputs/(qid+'.review.json'),review);reviews.append(review)
            trace=pipeline.prepare(q['query'],review=review,trace_path=traces/(qid+'.json'))
            actual=trace['retrieval'];assert [(d['source_id'],d['cosine_distance']) for d in actual['sources']]==[(d['source_id'],d['cosine_distance']) for d in old[qid]['results']]
            assert actual['query_embedding']['cache_hit'] is True
            expected='insufficient' if not lab['references'] else 'partially_sufficient' if is_partial else 'sufficient'
            assert trace['assessment_before_selection']['status']==expected,(qid,trace['assessment_before_selection']['status'])
            ctx=trace['context_selection'];assert ctx['budget']['within_budget'] is True
            assert ctx['budget']['input_tokens']==pipeline.counter.count_messages(ctx['messages'])
            assert ctx['budget']['input_tokens']+ctx['budget']['reserved_output_tokens']+ctx['budget']['safety_margin_tokens']<=ctx['budget']['context_window_tokens']
            source_by_id={d['source_id']:r.read_source(d['source_id'])['document'] for d in actual['sources']}
            for e in trace['evidence_reading']['evidence']:
                doc=source_by_id[e['source_id']];assert doc['content'][e['start']:e['end']]==e['quote'];context=e['source_context'];assert doc['content'][context['start']:context['end']]==context['text']
                for a in context.get('ancestor_introductions',[]):assert doc['content'][a['start']:a['end']]==a['text']
            for block in ctx['selected_blocks']:assert source_by_id[block['source_id']]['content'][block['start']:block['end']]==block['text']
            results.append(dict(question_id=qid,before=trace['assessment_before_selection']['status'],after=trace['assessment_after_selection']['status'],
                context_status=ctx['status'],input_tokens=ctx['budget']['input_tokens'],policy=trace['medical_policy_after_selection']['action']))
            saved[qid]=trace;print(qid,results[-1],flush=True)
        # A question's old evaluation label is never loaded by the default runtime.
        no_review=pipeline.prepare(questions[0]['query'],trace_path=traces/'Q01_without_review.json')
        assert no_review['assessment_before_selection']['assessment_state']=='pending_semantic_review';assert not no_review['context_selection']['selected_blocks']
        cfg=copy.deepcopy(pipeline.config);cfg.update(context_window_tokens=1024,reserved_output_tokens=128,safety_margin_tokens=64,max_evidence_tokens=512)
        tight=EvidencePipeline(r,config=cfg,counter=pipeline.counter).prepare(questions[14]['query'],review=reviews[14],trace_path=traces/'Q15_tight_budget.json')
        assert tight['assessment_after_selection']['status']!='sufficient';assert not tight['context_selection']['selected_blocks']
    # Synthetic conflict verifies engineering, not a contradiction among real medical sources.
    sys.path.insert(0,str(ROOT/'tests'))
    from test_evidence_context import QUESTION,document,retrieved,review_for
    synthetic_docs=[document(),document('TEST-B')];rv=review_for(synthetic_docs);rv['items'][1]['stance']='opposes'
    rv['conflicts']=[dict(claim_id='c1',item_ids=['i0','i1'],comparability_reviewed=True,rationale='SYNTHETIC TEST ONLY: intentionally opposing annotations, not medical evidence')]
    fixture_config=copy.deepcopy(pipeline.config);fixture_config['mode']='test_fixture'
    synthetic=EvidencePipeline(retriever=object(),config=fixture_config,counter=pipeline.counter).prepare_retrieved(QUESTION,retrieved(synthetic_docs),review=rv)
    synthetic['trace_data_kind']='synthetic_fixture_not_database_not_clinical';assert synthetic['assessment_before_selection']['status']=='conflicting'
    atomic_json(traces/'SYNTHETIC_conflicting.json',synthetic)
    assert_frozen_json(inputs/'reference_replay_manifest.json',dict(kind='label_replay_fixture_not_clinical_gold',files={p.name:sha(p.read_bytes()) for p in inputs.glob('Q*.review.json')},source_frozen_inputs=frozen))
    test_output=io.StringIO();suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'));test_result=unittest.TextTestRunner(stream=test_output,verbosity=2).run(suite)
    (out/'tests.txt').write_text(test_output.getvalue(),encoding='utf-8');assert test_result.wasSuccessful(),test_output.getvalue()
    after=snapshot(r);atomic_json(out/'after.json',after);assert after==before
    assert all(sha((ROOT/n).read_bytes())==v for n,v in protected.items())
    summary=dict(status='verified',documents_before=33,documents_after=33,vectors_before=33,vectors_after=33,
        database_unchanged=True,protected_source_files_unchanged=132,existing_retrieval_code_and_config_unchanged=True,
        retrieval_regression_queries=30,ranks_and_distances_unchanged=True,query_api_calls=0,answer_generation_calls=0,
        all_exact_spans_and_selected_contexts_valid=True,all_normal_contexts_within_budget=True,
        evidence_state_counts_before=dict(collections.Counter(r['before'] for r in results)),evidence_state_counts_after=dict(collections.Counter(r['after'] for r in results)),
        results=results,unit_and_integration_tests_run=test_result.testsRun,tests_failed=len(test_result.failures),tests_errors=len(test_result.errors),tests_skipped=len(test_result.skipped),
        configured_model=pipeline.config['model_id'],tokenizer=pipeline.counter.profile,context_window_tokens=pipeline.config['context_window_tokens'],
        real_conflicting_clinical_case_validated=False,synthetic_conflict_logic_tested=True,autonomous_semantic_reader_implemented=False,
        reviewer_annotation_replay_not_independent_accuracy_score=True,independent_clinical_review=False,
        limitations=['Existing reviewed references exercise the pipeline; they are not independent semantic judgments.',
          'Default unreviewed questions remain pending/insufficient; no automatic clinical sufficiency inference.',
          'Conflicting case is synthetic only; no medical contradiction was invented.',
          'Hosted NVIDIA NIM token usage parity and endpoint window remain unverified; no generation call was made.'],
        dependency_versions={n:importlib.metadata.version(n) for n in ['transformers','tokenizers','jinja2','huggingface-hub']})
    atomic_json(out/'verification.json',summary);print('AUDIT_DIR='+str(out),flush=True);print('VERIFIED',json.dumps({k:v for k,v in summary.items() if k not in ['tokenizer','results']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
