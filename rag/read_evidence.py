"""Run automatic semantic reading, without a reference review or final patient answer."""
import argparse,getpass,json,sys
from pathlib import Path
from .retriever import PostgresRetriever,RetrievalError,atomic_json
from .evidence_pipeline import EvidencePipeline
from .semantic_reader import NimEvidenceReader,NimClient
from .semantic_reader_v3 import AtomicNeedsReader

def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser()
    p.add_argument('question',nargs='?');p.add_argument('--trace');p.add_argument('--cohere-key-file');p.add_argument('--prompt-cohere-key',action='store_true');p.add_argument('--nvidia-key-file');p.add_argument('--calibrate',action='store_true')
    p.add_argument('--reader-version',choices=['v2','v3'],default='v3')
    args=p.parse_args();secret=None
    if not args.calibrate and not args.question:p.error('question is required unless --calibrate')
    try:
        r=PostgresRetriever(key_file=args.cohere_key_file)
        if not args.calibrate:r.health()
        if args.prompt_cohere_key:
            secret=getpass.getpass('Cohere query API key (hidden): ');r.embedder.key_supplier=lambda:secret
        pipe=EvidencePipeline(r);reader_class=NimEvidenceReader if args.reader_version=='v2' or args.calibrate else AtomicNeedsReader
        reader=reader_class(counter=pipe.counter,key_file=args.nvidia_key_file);pipe.semantic_reader=reader
        if args.calibrate:
            record=reader.client.complete([{'role':'system','content':'Return one JSON object only.'},{'role':'user','content':'Return exactly {"ok":true}.'}])
            result={k:v for k,v in record.items() if k not in ['identity','content']}
            result.update(status='ok',calibration_only=True,patient_answer_generated=False)
            if args.trace:atomic_json(args.trace,result)
        else:
            trace=pipe.prepare(args.question,trace_path=args.trace)
            result=dict(status='ok',trace=str(Path(args.trace).resolve()) if args.trace else None,
                assessment=trace['assessment_after_selection'],policy=trace['medical_policy_after_selection'],
                context_status=trace['context_selection']['status'],context_token_budget=trace['context_selection']['budget'],
                reader_provider=trace['semantic_reader']['provider'],reader_protocol=trace['semantic_reader'].get('protocol','passage_ids_v2'),model_calls=trace['semantic_reader'].get('calls',[]),generation_enabled=False)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except RetrievalError as exc:
        result=dict(status='error',error_code=exc.code,message=str(exc),reader_provider=getattr(exc,'reader_telemetry',None),error_stage=getattr(exc,'stage',None),model_calls=getattr(exc,'reader_calls',[]),generation_enabled=False)
        if args.trace:atomic_json(args.trace,result)
        print(json.dumps(result,ensure_ascii=False));return 1
    finally:secret=None
if __name__=='__main__':sys.exit(main())
