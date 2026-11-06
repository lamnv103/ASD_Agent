import argparse,getpass,json,sys
from .retriever import PostgresRetriever,RetrievalError

def main():
    parser=argparse.ArgumentParser(description="Read-only PostgreSQL/Cohere whole-document retrieval")
    parser.add_argument("--config");parser.add_argument("--database-env");parser.add_argument("--key-file");parser.add_argument("--prompt-key",action="store_true")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("health")
    p=sub.add_parser("search");p.add_argument("query");p.add_argument("--top-k",type=int,default=5);p.add_argument("--full-content",action="store_true")
    p=sub.add_parser("source");p.add_argument("source_id")
    args=parser.parse_args(); secret=None
    try:
        if args.prompt_key: secret=getpass.getpass("Cohere API key (hidden): ")
        retriever=PostgresRetriever(args.config,database_env=args.database_env,key_file=args.key_file,key_supplier=(lambda:secret) if secret else None)
        if args.command=="health": result=retriever.health()
        elif args.command=="source": result=retriever.read_source(args.source_id)
        else: result=retriever.retrieve(args.query,args.top_k,include_content=args.full_content)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except RetrievalError as exc:
        print(json.dumps(dict(status="error",error_code=exc.code,message=str(exc)),ensure_ascii=False));return 1
    finally: secret=None
if __name__=="__main__":sys.exit(main())
