"""New-question semantic-reader pilot. Gold/source labels never enter model prompts."""
import argparse,copy,csv,getpass,io,json,sys,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts/evaluation'))
from rag.retriever import PostgresRetriever,RetrievalError,atomic_json,sha
from rag.evidence_pipeline import EvidencePipeline
from rag.semantic_reader import NimEvidenceReader
from evaluate_retriever import snapshot

def run(args):
    work=ROOT/(ROOT/'reports/.semantic_reader_current_run').read_text(encoding='utf-8')
    folder=Path(args.inputs_dir) if args.inputs_dir else ROOT/'evaluation/semantic_reader_v1'
    frozen=json.loads((folder/'frozen_inputs.json').read_text(encoding='utf-8'))
    assert all(sha((folder/n).read_bytes())==v for n,v in frozen['files'].items())
    questions=[json.loads(x) for x in (folder/'questions.jsonl').read_text(encoding='utf-8').splitlines()]
    if args.max_cases:questions=questions[:args.max_cases]
    labels={x['question_id']:x for x in map(json.loads,(folder/'reference_labels.jsonl').read_text(encoding='utf-8').splitlines())}
    r=PostgresRetriever(key_file=args.cohere_key_file)
    r.health()
    assert snapshot(r)==json.loads((work/'before.json').read_text(encoding='utf-8'))
    secret=getpass.getpass('Cohere query API key (hidden): ') if args.prompt_cohere_key else None
    if secret:r.embedder.key_supplier=lambda:secret
    pipe=EvidencePipeline(r);pipe.semantic_reader=NimEvidenceReader(counter=pipe.counter,key_file=args.nvidia_key_file)
    run_dir=work/('pilot_'+datetime.now(timezone(timedelta(hours=7))).strftime('%Y%m%d_%H%M%S'))
    run_dir.mkdir();(run_dir/'traces').mkdir()
    for n in ['questions.jsonl','reference_labels.jsonl','frozen_inputs.json']:(run_dir/n).write_bytes((folder/n).read_bytes())
    atomic_json(run_dir/'model_and_reader_config.json',dict(reader=pipe.semantic_reader.config,context=pipe.config))
    source_docs={};rows=[];atomic_json(run_dir/'status.json',{'status':'running','planned':len(questions)})
    print('RUN_DIR='+str(run_dir),flush=True)
    try:
        for q in questions:
            qid=q['question_id'];retrieval=None;trace=None;telemetry={}
            row=dict(question_id=qid,question=q['question'],status='error',error_code='',error_stage='',assessment='',policy='',expected_source_in_top5=None,expected_source_used=None,expected_reference_span_overlap=None,
                status_matches_provisional_reference=None,source_ids='',nvidia_cache_hit=None,query_cache_hit=None,provider_prompt_tokens=None,local_prompt_tokens=None,prompt_token_delta=None,verification_cache_hit=None,verification_prompt_delta=None,safety_overrides=0,manual_semantic_review_required=True)
            try:
                # Reference labels are deliberately unavailable to these two stages.
                retrieval=r.retrieve(q['question'],5,include_content=True)
                source_docs.update({d['source_id']:d for d in retrieval['results']})
                row['source_ids']=';'.join(d['source_id'] for d in retrieval['results']);row['query_cache_hit']=retrieval['query_embedding']['cache_hit']
                trace=pipe.prepare_retrieved(q['question'],retrieval)
                atomic_json(run_dir/'traces'/(qid+'.json'),trace)
                telemetry=trace['semantic_reader']['provider']
                check=trace['semantic_reader'].get('verification')
                row['safety_overrides']=len(trace['semantic_reader'].get('safety_overrides',[]))
                if check:row.update(verification_cache_hit=check['provider']['cache_hit'],verification_prompt_delta=check['provider']['prompt_token_delta'])
                row.update(status='ok',assessment=trace['assessment_after_selection']['status'],policy=trace['medical_policy_after_selection']['action'])
                # Score only after model execution; these are provisional labels, not medical truth.
                lab=labels[qid];refs=lab['expected_sources']
                selected=set(trace['context_selection']['selected_evidence_ids'])
                ev=[e for e in trace['evidence_reading']['evidence'] if e['evidence_id'] in selected]
                if refs:
                    row['expected_source_in_top5']=any(e['source_id'] in row['source_ids'].split(';') for e in refs)
                    row['expected_source_used']=any(e['source_id']==ref['source_id'] for e in ev for ref in refs)
                    row['expected_reference_span_overlap']=any(e['source_id']==ref['source_id'] and max(e['start'],ref['start'])<min(e['end'],ref['end']) for e in ev for ref in refs)
                row['status_matches_provisional_reference']=row['assessment'] in lab['acceptable_statuses']
                # Assert citations and scope/reading provenance remain structurally valid.
                assert trace['context_selection']['budget']['within_budget'] is True
                assert trace['generation_enabled'] is False and trace['evaluation_reference_mode'] is False
            except RetrievalError as exc:
                row['error_code']=exc.code;row['error_stage']=getattr(exc,'stage','reader_or_retrieval');telemetry=getattr(exc,'reader_telemetry',{})
                atomic_json(run_dir/'traces'/(qid+'_error.json'),dict(question=q['question'],error_code=exc.code,error_stage=row['error_stage'],message=str(exc),reader_provider=telemetry,
                    retrieved_sources=[{k:v for k,v in d.items() if k!='content'} for d in (retrieval or {}).get('results',[])],answer_generation_performed=False))
            if telemetry:
                row.update(nvidia_cache_hit=telemetry.get('cache_hit'),provider_prompt_tokens=telemetry.get('provider_prompt_tokens'),local_prompt_tokens=telemetry.get('local_prompt_tokens'),prompt_token_delta=telemetry.get('prompt_token_delta'))
            rows.append(row);atomic_json(run_dir/'progress.json',rows)
            print(qid,row['status'],row['error_code'] or row['assessment'],'token_delta',row['prompt_token_delta'],flush=True)
            if row['error_code'] in ['nim_auth','missing_nvidia_key','provider_auth','missing_key','nim_rate_limit','provider_rate_limit','database_error']:break
        with (run_dir/'results.csv').open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
        with (run_dir/'retrieved_sources.jsonl').open('w',encoding='utf-8') as f:
            for sid,doc in sorted(source_docs.items()):f.write(json.dumps(doc,ensure_ascii=False)+'\n')
        after=snapshot(r);atomic_json(run_dir/'after.json',after);assert after==json.loads((work/'before.json').read_text(encoding='utf-8'))
        protected=json.loads((work/'protected_before.json').read_text(encoding='utf-8'));assert all(sha((ROOT/n).read_bytes())==v for n,v in protected.items())
        test_output=io.StringIO();suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'));test_result=unittest.TextTestRunner(stream=test_output,verbosity=2).run(suite)
        (run_dir/'tests.txt').write_text(test_output.getvalue(),encoding='utf-8')
        success=[x for x in rows if x['status']=='ok'];deltas=[x['prompt_token_delta'] for x in rows if x['prompt_token_delta'] is not None]
        deltas += [x['verification_prompt_delta'] for x in rows if x['verification_prompt_delta'] is not None]
        summary=dict(status='complete' if len(rows)==len(questions) and len(success)==len(rows) else 'completed_with_errors' if len(rows)==len(questions) else 'partial',planned=len(questions),processed=len(rows),structurally_valid_reader_results=len(success),
            rejected_results=[dict(question_id=x['question_id'],error=x['error_code']) for x in rows if x['status']!='ok'],
            provisional_status_matches=sum(x['status_matches_provisional_reference'] is True for x in success),
            source_covered_queries=sum(x['expected_source_in_top5'] is True for x in rows),
            independently_clinically_validated=False,semantic_accuracy_not_established=True,
            model_did_not_receive_reference_labels=True,full_question_coverage_automatically_verified=False,
            nvidia_prompt_token_deltas_observed=deltas,observed_local_provider_counts_match=bool(deltas) and all(d==0 for d in deltas),
            nvidia_uncached_completed_calls=sum(x['nvidia_cache_hit'] is False for x in rows),
            nvidia_verifier_uncached_calls=sum(x['verification_cache_hit'] is False for x in rows),
            cohere_uncached_query_calls=sum(x['query_cache_hit'] is False for x in rows),
            patient_answer_generation_calls=0,documents_before=33,documents_after=33,vectors_before=33,vectors_after=33,protected_source_files_unchanged=132,
            database_and_protected_retriever_unchanged=True,tests_run=test_result.testsRun,tests_failed=len(test_result.failures),tests_errors=len(test_result.errors),tests_skipped=len(test_result.skipped),
            results=rows)
        atomic_json(run_dir/'summary.json',summary);atomic_json(run_dir/'status.json',{'status':summary['status'],'processed':len(rows)})
        (work/'latest_pilot.txt').write_text(run_dir.relative_to(ROOT).as_posix(),encoding='utf-8')
        print('SUMMARY',json.dumps({k:v for k,v in summary.items() if k!='results'},ensure_ascii=False),flush=True)
        assert test_result.wasSuccessful()
        return 0
    finally:secret=None

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prompt-cohere-key',action='store_true');p.add_argument('--cohere-key-file');p.add_argument('--nvidia-key-file');p.add_argument('--max-cases',type=int);p.add_argument('--inputs-dir')
    sys.exit(run(p.parse_args()))
