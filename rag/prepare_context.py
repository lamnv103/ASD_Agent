"""Prepare an auditable evidence/context trace. Does not generate an answer."""
import argparse,json,sys
from pathlib import Path
from .retriever import RetrievalError,atomic_json
from .evidence_pipeline import EvidencePipeline

def main():
    p=argparse.ArgumentParser();p.add_argument('question');p.add_argument('--review-file');p.add_argument('--config');p.add_argument('--key-file');p.add_argument('--top-k',type=int,default=5);p.add_argument('--trace')
    args=p.parse_args()
    try:
        config=json.loads(Path(args.config).read_text(encoding='utf-8')) if args.config else None
        review=json.loads(Path(args.review_file).read_text(encoding='utf-8')) if args.review_file else None
        from .retriever import PostgresRetriever
        pipeline=EvidencePipeline(PostgresRetriever(key_file=args.key_file),config=config)
        result=pipeline.prepare(args.question,top_k=args.top_k,review=review,trace_path=args.trace)
        if args.trace:
            print(json.dumps(dict(trace=str(Path(args.trace).resolve()),assessment_before=result['assessment_before_selection']['status'],
                assessment_after=result['assessment_after_selection']['status'],assessment_state=result['assessment_after_selection']['assessment_state'],
                context_status=result['context_selection']['status'],token_budget=result['context_selection']['budget'],generation_enabled=False),ensure_ascii=False,indent=2))
        else:print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except RetrievalError as exc:
        print(json.dumps(dict(status='error',error_code=exc.code,message=str(exc)),ensure_ascii=False));return 1
    except (OSError,ValueError,TypeError,KeyError):
        print(json.dumps(dict(status='error',error_code='input_file_invalid',message='Invalid configuration/review input; no context produced.')));return 1
if __name__=='__main__':sys.exit(main())
