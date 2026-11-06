"""Evaluate atomic-needs reader; frozen references are used only AFTER model execution."""
from __future__ import annotations
import argparse,csv,getpass,json,sys,time
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'scripts/evaluation'))
from rag.retriever import PostgresRetriever,RetrievalError,atomic_json,sha
from rag.evidence_pipeline import EvidencePipeline
from rag.semantic_reader_v3 import AtomicNeedsReader
from evaluate_retriever import snapshot

def run(args):
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    work=ROOT/(ROOT/'reports/.reader_refinement_current_run').read_text(encoding='utf-8')
    folder=(ROOT/args.inputs).resolve();frozen=json.loads((folder/'frozen_inputs.json').read_text(encoding='utf-8'))
    assert all(sha((folder/p).read_bytes())==v for p,v in frozen['files'].items())
    questions=[json.loads(s) for s in (folder/'questions.jsonl').read_text(encoding='utf-8').splitlines()]
    if args.ids:
        requested=set(args.ids.split(','));questions=[q for q in questions if q['question_id'] in requested]
        assert {q['question_id'] for q in questions}==requested
    assert questions
    # Load labels for scoring only; never pass this object into retrieval/reader.
    labels={d['question_id']:d for d in map(json.loads,(folder/'reference_labels.jsonl').read_text(encoding='utf-8').splitlines())}
    secret=getpass.getpass('Cohere query key (hidden): ') if args.prompt_cohere_key else None
    r=PostgresRetriever(key_file=args.cohere_key_file,key_supplier=(lambda:secret) if secret else None)
    r.health();before=snapshot(r);assert before==json.loads((work/'before.json').read_text(encoding='utf-8'))
    pipe=EvidencePipeline(r);pipe.semantic_reader=AtomicNeedsReader(counter=pipe.counter)
    out=work/('run_'+datetime.now(timezone(timedelta(hours=7))).strftime('%Y%m%d_%H%M%S_%f'));out.mkdir();(out/'traces').mkdir()
    for n in ['questions.jsonl','reference_labels.jsonl','frozen_inputs.json']:(out/n).write_bytes((folder/n).read_bytes())
    code_files=['rag/semantic_reader_v3.py','rag/semantic_reader.py','rag/evidence.py','rag/context.py','rag/read_evidence.py','deployments/semantic_reader_v3.json','scripts/evaluation/evaluate_reader_v3.py']
    atomic_json(out/'implementation.json',dict(files={p:sha((ROOT/p).read_bytes()) for p in code_files},config=pipe.semantic_reader.config))
    rows=[];atomic_json(out/'status.json',dict(status='running',planned=len(questions)))
    print('RUN_DIR='+str(out),flush=True)
    try:
        for q in questions:
            qid=q['question_id'];tick=time.monotonic();retrieval=None;calls=[]
            row=dict(question_id=qid,question=q['question'],status='error',error_code='',error_stage='',assessment='',policy='',top5_sources=[],expected_source_in_top5=None,
                expected_source_used=None,reference_span_overlap_sent=None,reference_span_overlap_used=None,reference_units_total=0,reference_units_fully_sent=0,reference_status_agreement=None,need_count=0,
                missing_required_needs=[],selected_evidence_count=0,query_cache_hit=None,model_calls=[],elapsed_seconds=None)
            try:
                retrieval=r.retrieve(q['question'],5,include_content=True)
                row['top5_sources']=[d['source_id'] for d in retrieval['results']];row['query_cache_hit']=retrieval['query_embedding']['cache_hit']
                trace=pipe.prepare_retrieved(q['question'],retrieval)
                atomic_json(out/'traces'/(qid+'.json'),trace)
                calls=trace['semantic_reader']['calls']
                a=trace['assessment_after_selection'];row.update(status='ok',assessment=a['status'],policy=trace['medical_policy_after_selection']['action'],
                    need_count=len(a['claims']),missing_required_needs=a['missing_claims'],selected_evidence_count=len(trace['context_selection']['selected_evidence_ids']))
                refs=labels[qid]['expected_sources'];row['reference_status_agreement']=a['status'] in labels[qid]['acceptable_statuses']
                sent=[(e['source_id'],p['start'],p['end']) for e in trace['semantic_reader']['excerpts'] for p in e['passages']]
                selected=set(trace['context_selection']['selected_evidence_ids']);used=[e for e in trace['evidence_reading']['evidence'] if e['evidence_id'] in selected and e['stance']!='context_only']
                row['reference_units_total']=len(refs)
                ranges=[(e['source_id'],e['start'],e['end']) for e in trace['semantic_reader']['excerpts']]
                def fully_sent(ref):
                    pos=ref['start']
                    for sid,a,b in sorted(ranges,key=lambda x:x[1]):
                        if sid!=ref['source_id'] or b<=pos:continue
                        if a>pos:return False
                        pos=max(pos,b)
                        if pos>=ref['end']:return True
                    return False
                row['reference_units_fully_sent']=sum(fully_sent(ref) for ref in refs)
                if refs:
                    row['expected_source_in_top5']=any(ref['source_id'] in row['top5_sources'] for ref in refs)
                    row['expected_source_used']=any(e['source_id']==ref['source_id'] for e in used for ref in refs)
                    row['reference_span_overlap_sent']=any(sid==ref['source_id'] and max(a,ref['start'])<min(b,ref['end']) for sid,a,b in sent for ref in refs)
                    row['reference_span_overlap_used']=any(e['source_id']==ref['source_id'] and max(e['start'],ref['start'])<min(e['end'],ref['end']) for e in used for ref in refs)
                assert trace['context_selection']['budget']['within_budget'] is True and trace['generation_enabled'] is False
                assert trace['evaluation_reference_mode'] is False
            except RetrievalError as exc:
                calls=getattr(exc,'reader_calls',[])
                row.update(error_code=exc.code,error_stage=getattr(exc,'stage','retrieval'))
                atomic_json(out/'traces'/(qid+'_error.json'),dict(question=q['question'],error_code=exc.code,error_stage=row['error_stage'],message=str(exc),reader_calls=calls,generation_enabled=False))
            if retrieval is not None and labels[qid]['expected_sources']:
                row['expected_source_in_top5']=any(ref['source_id'] in row['top5_sources'] for ref in labels[qid]['expected_sources'])
            row['model_calls']=calls;row['elapsed_seconds']=round(time.monotonic()-tick,3);rows.append(row)
            atomic_json(out/'progress.json',rows)
            print(qid,row['status'],row['assessment'] or row['error_code'],'needs',row['need_count'],'seconds',row['elapsed_seconds'],flush=True)
            if row['error_code'] in {'provider_auth','nim_auth','provider_rate_limit','nim_rate_limit','missing_key','missing_nvidia_key','database_error'}:break
        after=snapshot(r);assert after==before
        protected=json.loads((work/'protected_before.json').read_text(encoding='utf-8'));assert all(sha((ROOT/p).read_bytes())==h for p,h in protected.items())
        atomic_json(out/'after.json',after)
        with (out/'results.csv').open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader()
            writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(list,dict)) else v for k,v in row.items()} for row in rows)
        good=[x for x in rows if x['status']=='ok'];calls=[c for row in rows for c in row['model_calls']]
        summary=dict(status='complete' if len(good)==len(questions) else 'completed_with_errors' if len(rows)==len(questions) else 'partial',
            planned=len(questions),processed=len(rows),valid_traces=len(good),errors=[dict(question_id=x['question_id'],error=x['error_code'],stage=x['error_stage']) for x in rows if x['status']!='ok'],
            provisional_label_agreement=sum(x['reference_status_agreement'] is True for x in good),
            disagreements=[x['question_id'] for x in good if not x['reference_status_agreement']],
            expected_source_questions=sum(bool(labels[q['question_id']]['expected_sources']) for q in questions),
            expected_source_top5_hits=sum(x['expected_source_in_top5'] is True for x in rows),
            completed_nim_stages=len(calls),uncached_completed_nim_stages=sum(c.get('cache_hit') is False for c in calls),
            uncached_query_embeddings=sum(x['query_cache_hit'] is False for x in rows),prompt_token_deltas=sorted({c['prompt_token_delta'] for c in calls}),
            documents=33,vectors=33,source_files_unchanged=132,database_unchanged=True,patient_answer_generation_calls=0,
            independent_clinical_validation=False,semantic_accuracy_established=False,results=rows)
        atomic_json(out/'summary.json',summary);atomic_json(out/'status.json',dict(status=summary['status']))
        print('SUMMARY',json.dumps({k:v for k,v in summary.items() if k!='results'},ensure_ascii=False),flush=True)
        return 0 if summary['status']=='complete' else 1
    finally:secret=None

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inputs',default='evaluation/reader_v3_development');p.add_argument('--ids');p.add_argument('--prompt-cohere-key',action='store_true');p.add_argument('--cohere-key-file')
    sys.exit(run(p.parse_args()))
