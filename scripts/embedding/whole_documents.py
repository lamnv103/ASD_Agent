"""Whole-document Cohere embeddings and additive PostgreSQL collection. No chunking."""
from __future__ import annotations
import argparse,csv,getpass,io,json,math,os,ssl,sys,time,struct
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib import request,error
from dotenv import dotenv_values
import psycopg2
from psycopg2.extras import Json
from psycopg2 import sql
from smoke_test_nim import sha,atomic_json,validate_vector,NoRedirect,PilotError

ROOT=Path(__file__).resolve().parents[2];LIB=ROOT/'knowledge/rag/source_library'
REPORT=ROOT/'reports/whole_document_embedding_20261030'
MODEL='embed-v4.0';DIM=1536;ENDPOINT='https://api.cohere.com/v2/embed'
PROFILE=dict(provider='cohere',model=MODEL,dimensions=DIM,document_input_type='search_document',query_input_type='search_query',truncate='NONE',
 max_tokens=128000,whole_document=True,pooling='native_model_single_input',schema_version=1)
SPACE='cohere4_whole_1536_'+sha(json.dumps(PROFILE,sort_keys=True))[:12]
DEFAULT_DB_ENV=ROOT/'deployments/database.env'

def now():return datetime.now(timezone(timedelta(hours=7))).isoformat(timespec='seconds')

class ProviderRejected(PilotError):
 def __init__(self,code,retry_after=None):
  self.code=code;self.retry_after=retry_after
  super().__init__('Cohere HTTP '+str(code)+'; provider rejected request; credentials omitted.')

def journal(event):
 REPORT.mkdir(parents=True,exist_ok=True)
 with (REPORT/'request_events.jsonl').open('a',encoding='utf-8') as stream:
  stream.write(json.dumps(dict(recorded_at=now(),**event),ensure_ascii=False)+chr(10));stream.flush();os.fsync(stream.fileno())

def rate_wait(collection,body):
 # This is only a conservative pacing heuristic, NEVER a provider token count.
 expected=math.ceil(len(body.encode('utf-8'))/2.8)+2048
 expected=min(expected,95000)
 while True:
  recent=[]
  for path in (REPORT/'vectors'/collection/SPACE).glob('*.json'):
   if path.name.endswith('.attempt.json'):continue
   item=json.loads(path.read_text(encoding='utf-8'))
   age=datetime.now(timezone.utc).timestamp()-datetime.fromisoformat(item['created_at']).timestamp()
   if age<65:
    tokens=(item.get('usage_meta') or {}).get('billed_units',{}).get('input_tokens',0)
    recent.append((age,tokens))
  if not recent or sum(t for age,t in recent)+expected<=95000:return
  delay=min(30,max(1,math.ceil(min(65-age for age,tokens in recent))))
  print('Pacing for token-rate budget:',delay,'seconds; completed vectors retained.',flush=True)
  time.sleep(delay)


def load_source():
 raw=(LIB/'documents.json').read_bytes();state=json.loads((LIB/'BUILD_STATUS.json').read_text(encoding='utf-8'))
 if state.get('status')!='verified' or not state.get('usable') or sha(raw)!=state['documents_json_sha256']:raise PilotError('Source release/hash is not verified.')
 docs=json.loads(raw)['tai_lieu']
 if len(docs)!=33 or len({d['id'] for d in docs})!=33:raise PilotError('Expected 33 unique complete documents.')
 for d in docs:
  if sha(d['noi_dung'])!=d['doi_chieu']['sha256_noi_dung'] or not d['noi_dung'].strip():raise PilotError('Source content mismatch: '+d['id'])
  if any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-' for c in d['id']):raise PilotError('Unsafe source identifier.')
  if d['doi_chieu'].get('da_tham_dinh_lam_sang_doc_lap'):raise PilotError('Unexpected clinical approval change; review release.')
 manifest=json.loads((LIB/'SUPPLEMENT_20261030_MANIFEST.json').read_text(encoding='utf-8'))
 for name,info in manifest['files'].items():
  path=(ROOT/name).resolve()
  if not path.is_relative_to(LIB.resolve()) or sha(path.read_bytes())!=info['sha256']:raise PilotError('Protected source manifest mismatch.')
 return sorted(docs,key=lambda d:len(d['noi_dung'])),sha(raw),'asd_fulltext_33_20261030_'+sha(raw)[:12]

def connection(env_file,readonly=False):
 cfg=dotenv_values(env_file,interpolate=False);dsn=cfg.get('RAG_DATABASE_URL')
 if not dsn:raise PilotError('Missing RAG_DATABASE_URL in supplied database env file.')
 try:conn=psycopg2.connect(dsn,connect_timeout=5,options='-c statement_timeout=20000 -c lock_timeout=5000')
 except Exception:raise PilotError('Cannot connect to configured RAG PostgreSQL; credential details omitted.') from None
 if conn.info.dbname!='asd_rag':conn.close();raise PilotError('Expected database asd_rag; refused another database.')
 if readonly:conn.set_session(readonly=True,autocommit=True)
 return conn

def legacy_snapshot(conn,collection):
 queries={
  'collections':('select md5(row_to_json(t)::text) from carobud_rag.collections t where collection_id<>%s order by 1',(collection,)),
  'documents':('select md5(row_to_json(t)::text) from carobud_rag.documents t where collection_id<>%s order by 1',(collection,)),
  'embedding_spaces':('select md5(row_to_json(t)::text) from carobud_rag.embedding_spaces t where space_id<>%s order by 1',(SPACE,)),
  'embeddings':('select md5(row_to_json(t)::text) from carobud_rag.embeddings t where collection_id<>%s order by 1',(collection,)),
  'curated_chunks':('select md5(row_to_json(t)::text) from asd_knowledge_v2_pilot.chunks t order by 1',())}
 out={}
 with conn.cursor() as c:
  for name,(sql,params) in queries.items():
   c.execute(sql,params);values=[r[0] for r in c.fetchall()];out[name]=dict(rows=len(values),row_hashes_sha256=sha(json.dumps(values)))
 return out

def check_backup_and_baseline(conn,collection):
 backup=REPORT/'postgres_before.dump'
 if not backup.is_file() or backup.read_bytes()[:5]!=b'PGDMP':raise PilotError('A validated pg_dump backup is required before database writes.')
 snapshot=legacy_snapshot(conn,collection);path=REPORT/'legacy_before.json'
 if path.exists():
  if json.loads(path.read_text(encoding='utf-8'))!=snapshot:raise PilotError('Legacy database changed relative to saved baseline; review before mutation.')
 else:atomic_json(path,snapshot)
 atomic_json(REPORT/'backup.json',dict(file=backup.relative_to(ROOT).as_posix(),sha256=sha(backup.read_bytes()),bytes=backup.stat().st_size,format='PostgreSQL pg_dump custom',database='asd_rag',created_before_this_collection=True))

def check_legacy(conn,collection):
 before=json.loads((REPORT/'legacy_before.json').read_text(encoding='utf-8'))
 after=legacy_snapshot(conn,collection)
 if before!=after:raise PilotError('Legacy row hash mismatch.')
 return after

def preflight():
 docs,dataset,collection=load_source()
 rows=[dict(source_id=d['id'],title=d['ten_tai_lieu'],characters=len(d['noi_dung']),utf8_bytes=len(d['noi_dung'].encode('utf-8')),
  whitespace_words=len(d['noi_dung'].split()),content_sha256=sha(d['noi_dung']),provider_token_count=None,
  token_status='not_counted_by_selected_provider; not inferred from characters/words',embedding_status='pending_native_full_input') for d in docs]
 out=dict(status='ready_for_provider_validation',documents=33,body_characters=sum(r['characters'] for r in rows),dataset_sha256=dataset,collection_id=collection,
  embedding_space=SPACE,profile=PROFILE,nvidia_current_hosted_limit_tokens=10240,
  token_limit_reference='https://docs.cohere.com/docs/cohere-embed',truncate='NONE',chunking=False,source_documents_unchanged=True,documents_detail=rows)
 atomic_json(REPORT/'preflight.json',out)
 buff=io.StringIO(newline='');writer=csv.DictWriter(buff,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 (REPORT/'document_lengths.csv').write_text('\ufeff'+buff.getvalue(),encoding='utf-8')
 return dict(status=out['status'],documents=33,collection_id=collection,model=MODEL,dimensions=DIM)

def stage_text(db_env):
 docs,dataset,collection=load_source();conn=connection(db_env)
 try:
  check_backup_and_baseline(conn,collection)
  with conn:
   with conn.cursor() as c:
    c.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))',(collection,))
    c.execute('insert into carobud_rag.collections(collection_id,corpus_sha256) values(%s,%s) on conflict do nothing',(collection,dataset))
    c.execute('select corpus_sha256 from carobud_rag.collections where collection_id=%s',(collection,))
    if c.fetchone()[0]!=dataset:raise PilotError('Existing collection has another dataset hash.')
    for d in docs:
     metadata={k:v for k,v in d.items() if k!='noi_dung'}
     metadata.update(whole_document=True,clinical_reviewed=False,production_ingest=False,source_release_sha256=dataset,embedding_status='pending')
     identifier='whole-document:'+d['id']
     c.execute('insert into carobud_rag.documents(collection_id,chunk_id,source_id,content,content_sha256,metadata,search_text,prototype_ingest,production_ingest,enabled) values(%s,%s,%s,%s,%s,%s,%s,true,false,false) on conflict do nothing',
      (collection,identifier,d['id'],d['noi_dung'],sha(d['noi_dung']),Json(metadata),d['ten_tai_lieu']+'\n'+d['noi_dung']))
     c.execute('select source_id,content,content_sha256 from carobud_rag.documents where collection_id=%s and chunk_id=%s',(collection,identifier))
     if c.fetchone()!=(d['id'],d['noi_dung'],sha(d['noi_dung'])):raise PilotError('Existing document differs; no overwrite performed.')
    c.execute('select count(*) from carobud_rag.documents where collection_id=%s',(collection,))
    if c.fetchone()[0]!=33:raise PilotError('Unexpected source count in new collection.')
   check_legacy(conn,collection)
 finally:conn.close()
 return verify(db_env,allow_pending=True)

def api_payload(body,input_type):
 return dict(model=MODEL,texts=[body],input_type=input_type,embedding_types=['float'],output_dimension=DIM,truncate='NONE',max_tokens=128000)

def key_from_args(args):
 if args.prompt_key:
  key=getpass.getpass('COHERE_API_KEY (hidden, not saved): ').strip()
 elif args.cohere_env:
  key=(dotenv_values(args.cohere_env,interpolate=False).get('COHERE_API_KEY') or '').strip()
 else:key=os.environ.get('COHERE_API_KEY','').strip()
 if not key or key.startswith('nvapi-') or any(c.isspace() for c in key):raise PilotError('A valid COHERE_API_KEY is required; NVIDIA credentials are not sent to Cohere.')
 return key

def api_embed(body,key,input_type,timeout=60):
 payload=api_payload(body,input_type);raw=json.dumps(payload,ensure_ascii=False).encode('utf-8')
 if json.loads(raw)['texts']!=[body]:raise PilotError('Serialized input differs from whole source.')
 import certifi
 context=ssl.create_default_context(cafile=certifi.where())
 client=request.build_opener(NoRedirect(),request.HTTPSHandler(context=context))
 req=request.Request(ENDPOINT,data=raw,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json'},method='POST')
 try:
  with client.open(req,timeout=timeout) as resp:
   data=resp.read(8*1024*1024+1)
 except error.HTTPError as exc:
  header=exc.headers.get('Retry-After','') if exc.headers else ''
  delay=float(header) if header.replace('.','',1).isdigit() else None
  raise ProviderRejected(exc.code,delay) from None
 except (TimeoutError,error.URLError,OSError):raise PilotError('Cohere network/TLS/timeout error; remote completion unknown; no automatic retry.') from None
 if len(data)>8*1024*1024:raise PilotError('Oversized provider response.')
 response=json.loads(data);vectors=response.get('embeddings',{}).get('float')
 if not isinstance(vectors,list) or len(vectors)!=1:raise PilotError('Provider did not return exactly one vector.')
 vector=vectors[0];validate_vector(vector)
 if len(vector)!=DIM:raise PilotError('Provider returned another dimension.')
 if response.get('texts') is not None and response['texts']!=[body]:raise PilotError('Provider returned a modified/truncated source echo.')
 return vector,dict(provider_request_id=response.get('id'),usage_meta=response.get('meta'),response_sha256=sha(data),
  response_text_echo_matches=True if response.get('texts') is not None else None,request_utf8_bytes=len(raw))

def cache_path(collection,source):return REPORT/'vectors'/collection/SPACE/(source+'.json')

def read_cached(path,doc,dataset,collection):
 if not path.is_file():raise PilotError('Whole-document vector missing: '+doc['id'])
 p=json.loads(path.read_text(encoding='utf-8'))
 expected=dict(status='success',source_id=doc['id'],content_sha256=sha(doc['noi_dung']),dataset_sha256=dataset,collection_id=collection,
  space_id=SPACE,profile=PROFILE,model=MODEL,dimensions=DIM,whole_document=True,input_characters=len(doc['noi_dung']),sent_characters=len(doc['noi_dung']),truncate='NONE')
 if any(p.get(k)!=v for k,v in expected.items()):raise PilotError('Whole-document cache/provenance mismatch: '+doc['id'])
 validate_vector(p.get('embedding'))
 if len(p['embedding'])!=DIM or p.get('embedding_sha256')!=sha(json.dumps(p['embedding'],separators=(',',':'))):raise PilotError('Cached vector hash/dimension mismatch.')
 return p

def embed_all(args):
 docs,dataset,collection=load_source()
 missing=[d for d in docs if not cache_path(collection,d['id']).exists()]
 key=key_from_args(args) if missing else None
 REPORT.mkdir(parents=True,exist_ok=True);lock=REPORT/'embedding.lock'
 try:
  with lock.open('x',encoding='utf-8') as stream:json.dump(dict(pid=os.getpid(),started_at=now(),collection=collection),stream)
 except FileExistsError:raise PilotError('An embedding run is locked; check its process first.') from None
 try:
  for index,d in enumerate(docs,1):
   path=cache_path(collection,d['id']);attempt=path.with_suffix('.attempt.json')
   if path.exists():read_cached(path,d,dataset,collection);print(f'[{index}/33] cached {d["id"]}',flush=True);continue
   if attempt.exists() and not args.retry_uncertain:
    previous=json.loads(attempt.read_text(encoding='utf-8'))
    if previous.get('status')!='retryable_rejected':raise PilotError('Previous attempt requires inspection: '+d['id']+'; no automatic duplicate request.')
   atomic_json(attempt,dict(status='started',source_id=d['id'],started_at=now(),content_sha256=sha(d['noi_dung']),model=MODEL))
   print(f'[{index}/33] sending FULL {d["id"]}: {len(d["noi_dung"])} characters',flush=True)
   rate_wait(collection,d['noi_dung'])
   started=time.monotonic()
   for retry in range(4):
    try:
     vector,details=api_embed(d['noi_dung'],key,'search_document');break
    except ProviderRejected as rejected:
     journal(dict(source_id=d['id'],event='provider_rejected',http_status=rejected.code,retry_number=retry))
     atomic_json(attempt,dict(status='retryable_rejected' if rejected.code==429 else 'rejected',source_id=d['id'],http_status=rejected.code,finished_at=now()))
     if rejected.code!=429 or retry==3:raise
     delay=max(60,rejected.retry_after or 60)
     if delay>300:raise PilotError('Provider asks for a longer pause; inspect rate limit before resuming.') from None
     print('HTTP 429: waiting',int(delay),'seconds before bounded retry; no completed vector repeated.',flush=True)
     while delay>0:
      part=min(30,delay);time.sleep(part);delay-=part
     atomic_json(attempt,dict(status='started',source_id=d['id'],started_at=now(),model=MODEL,retry_number=retry+1))
   journal(dict(source_id=d['id'],event='provider_success',provider_request_id=details.get('provider_request_id')))
   result=dict(status='success',source_id=d['id'],source_title=d['ten_tai_lieu'],source_url=d['nguon']['link_nguon'],created_at=now(),
    content_sha256=sha(d['noi_dung']),dataset_sha256=dataset,collection_id=collection,space_id=SPACE,profile=PROFILE,model=MODEL,endpoint=ENDPOINT,
    dimensions=DIM,whole_document=True,input_characters=len(d['noi_dung']),sent_characters=len(d['noi_dung']),truncate='NONE',
    elapsed_seconds=round(time.monotonic()-started,6),embedding=vector,embedding_sha256=sha(json.dumps(vector,separators=(',',':'))),**details)
   atomic_json(path,result);read_cached(path,d,dataset,collection)
   atomic_json(attempt,dict(status='success',source_id=d['id'],finished_at=now(),result_sha256=sha(path.read_bytes()),content_sha256=sha(d['noi_dung'])))
   print(f'[{index}/33] saved {d["id"]}: {DIM} dimensions, {result["elapsed_seconds"]} seconds',flush=True)
  summary=dict(status='all_33_native_vectors_cached',documents=33,collection=collection,space=SPACE,model=MODEL,dimensions=DIM,source_bodies_truncated=False,chunk_vectors_averaged=False,database_loaded=None,database_note='Embedding stage does not check DB; see database_verification.json')
  atomic_json(REPORT/'embedding_complete.json',summary);return summary
 finally:lock.unlink(missing_ok=True)

def load_vectors(db_env):
 docs,dataset,collection=load_source()
 cached={d['id']:read_cached(cache_path(collection,d['id']),d,dataset,collection) for d in docs}
 conn=connection(db_env)
 try:
  check_backup_and_baseline(conn,collection)
  with conn:
   with conn.cursor() as c:
    c.execute('select pg_advisory_xact_lock(hashtextextended(%s,0))',(collection,))
    c.execute('select count(*) from carobud_rag.documents where collection_id=%s',(collection,))
    if c.fetchone()[0]!=33:raise PilotError('Stage all 33 source documents before vector loading.')
    c.execute('insert into carobud_rag.embedding_spaces(space_id,profile,dimensions,verified) values(%s,%s,%s,false) on conflict do nothing',(SPACE,Json(PROFILE),DIM))
    c.execute('select profile,dimensions from carobud_rag.embedding_spaces where space_id=%s',(SPACE,))
    if c.fetchone()!=(PROFILE,DIM):raise PilotError('Embedding space collision.')
    for d in docs:
     vector=cached[d['id']]['embedding'];identifier='whole-document:'+d['id']
     c.execute('select content,content_sha256 from carobud_rag.documents where collection_id=%s and chunk_id=%s',(collection,identifier))
     if c.fetchone()!=(d['noi_dung'],sha(d['noi_dung'])):raise PilotError('Database body changed before vector load.')
     c.execute('insert into carobud_rag.embeddings(collection_id,chunk_id,space_id,dimensions,embedding) values(%s,%s,%s,%s,%s::vector) on conflict do nothing',
      (collection,identifier,SPACE,DIM,json.dumps(vector)))
     c.execute('select embedding::text from carobud_rag.embeddings where collection_id=%s and chunk_id=%s and space_id=%s',(collection,identifier,SPACE))
     actual=json.loads(c.fetchone()[0])
     expected=[struct.unpack('f',struct.pack('f',v))[0] for v in vector]
     if len(actual)!=DIM or any(not math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-8) for a,b in zip(actual,expected)):raise PilotError('Database vector value mismatch.')
    c.execute('select count(*) from carobud_rag.embeddings where collection_id=%s',(collection,))
    if c.fetchone()[0]!=33:raise PilotError('Expected exactly one embedding per document in this collection.')
    index_name='whole33_'+dataset[:12]+'_one_vector'
    c.execute(sql.SQL('CREATE UNIQUE INDEX IF NOT EXISTS {} ON carobud_rag.embeddings(collection_id,chunk_id) WHERE collection_id={}').format(sql.Identifier(index_name),sql.Literal(collection)))
    c.execute('update carobud_rag.embedding_spaces set verified=true where space_id=%s',(SPACE,))
    c.execute("update carobud_rag.documents set enabled=true,metadata=jsonb_set(metadata,'{embedding_status}','\"complete_whole_document\"'::jsonb) where collection_id=%s",(collection,))
   check_legacy(conn,collection)
 finally:conn.close()
 status=verify(db_env)
 atomic_json(REPORT/'active_collection.json',dict(collection_id=collection,space_id=SPACE,profile=PROFILE,document_count=33,query_input_type='search_query',clinical_reviewed=False,production_ingest=False))
 return status

def verify(db_env,allow_pending=False):
 docs,dataset,collection=load_source();conn=connection(db_env,readonly=True)
 try:
  with conn.cursor() as c:
   c.execute('select source_id,content,content_sha256,enabled,production_ingest from carobud_rag.documents where collection_id=%s',(collection,))
   rows=c.fetchall();actual={r[0]:r for r in rows}
   if len(rows)!=33 or set(actual)!={d['id'] for d in docs}:raise PilotError('Database must contain all 33 distinct sources.')
   for d in docs:
    row=actual[d['id']]
    if row[1]!=d['noi_dung'] or row[2]!=sha(d['noi_dung']) or row[4]:raise PilotError('Database source/prototype state mismatch.')
   c.execute('select space_id,dimensions,count(*) from carobud_rag.embeddings where collection_id=%s group by 1,2',(collection,));vectors=c.fetchall()
   c.execute('select profile,dimensions,verified from carobud_rag.embedding_spaces where space_id=%s',(SPACE,));space_state=c.fetchone()
   complete=vectors==[(SPACE,DIM,33)] and all(r[3] for r in rows) and space_state==(PROFILE,DIM,True)
   if not complete and (not allow_pending or vectors or any(r[3] for r in rows)):raise PilotError('Not a complete 33-document/33-vector collection.')
   old=check_legacy(conn,collection)
   c.execute('select count(*) from carobud_rag.documents where collection_id=%s group by source_id having count(*)<>1',(collection,))
   if c.fetchall():raise PilotError('Duplicate whole-document source.')
  status=dict(status='verified_33_documents_33_vectors' if complete else '33_full_documents_staged_vectors_pending',checked_at=now(),
   database='asd_rag',collection_id=collection,space_id=SPACE,documents=33,vectors=33 if complete else 0,enabled_for_retrieval=complete,
   model=MODEL,dimensions=DIM,one_document_one_vector=complete,whole_texts_match_exactly=True,source_file_sha256=dataset,
   legacy_data_unchanged=True,legacy=old,clinical_reviewed=False,production_ingest=False)
  atomic_json(REPORT/'database_verification.json',status);return status
 finally:conn.close()

def search(args):
 verify(args.db_env);docs,dataset,collection=load_source()
 if not args.query.strip():raise PilotError('Query must not be blank.')
 qfile=REPORT/'queries'/(sha(json.dumps(dict(query=args.query,space=SPACE),sort_keys=True))+'.json')
 if qfile.exists():
  query=json.loads(qfile.read_text(encoding='utf-8'));vector=query['embedding'];validate_vector(vector)
  if query.get('query')!=args.query or query.get('space_id')!=SPACE or query.get('model')!=MODEL or query.get('input_type')!='search_query' or len(vector)!=DIM:raise PilotError('Cached query embedding space/provenance mismatch.')
 else:
  key=key_from_args(args);vector,details=api_embed(args.query,key,'search_query')
  query=dict(query=args.query,space_id=SPACE,model=MODEL,input_type='search_query',embedding=vector,**details);atomic_json(qfile,query)
 conn=connection(args.db_env,readonly=True)
 try:
  with conn.cursor() as c:
   c.execute('select d.source_id,d.metadata,e.embedding <=> %s::vector as distance from carobud_rag.documents d join carobud_rag.embeddings e using(collection_id,chunk_id) join carobud_rag.embedding_spaces s using(space_id) where d.collection_id=%s and e.space_id=%s and s.verified and d.enabled order by distance,d.source_id limit %s',(json.dumps(vector),collection,SPACE,args.top_k))
   rows=c.fetchall()
  result=dict(status='success',query=args.query,collection=collection,model=MODEL,search='PostgreSQL pgvector exact cosine',results=[dict(source_id=sid,title=metadata['ten_tai_lieu'],source_url=metadata['nguon']['link_nguon'],cosine_distance=distance) for sid,metadata,distance in rows])
  atomic_json(REPORT/'last_search.json',result);return result
 finally:conn.close()

def read_database_source(args):
 verify(args.db_env);docs,dataset,collection=load_source()
 if args.source_id not in {d['id'] for d in docs}:raise PilotError('Source identifier is outside this whole-document collection.')
 conn=connection(args.db_env,readonly=True)
 try:
  with conn.cursor() as c:
   c.execute('select source_id,content,content_sha256,metadata from carobud_rag.documents where collection_id=%s and source_id=%s and enabled',(collection,args.source_id))
   row=c.fetchone()
  if not row:raise PilotError('Source was not found in enabled PostgreSQL collection.')
  return dict(source_id=row[0],content=row[1],content_sha256=row[2],metadata=row[3],retrieved_from='PostgreSQL',collection_id=collection)
 finally:conn.close()

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['preflight','stage-text','embed','load-vectors','verify','search','source','run'])
 parser.add_argument('--db-env',type=Path,default=DEFAULT_DB_ENV)
 parser.add_argument('--cohere-env',type=Path);parser.add_argument('--prompt-key',action='store_true');parser.add_argument('--retry-uncertain',action='store_true')
 parser.add_argument('--source-id',default='')
 parser.add_argument('--query',default='');parser.add_argument('--top-k',type=int,default=5)
 args=parser.parse_args()
 if not 1<=args.top_k<=33:parser.error('top-k must be in 1..33')
 try:
  if args.command=='preflight':out=preflight()
  elif args.command=='stage-text':out=stage_text(args.db_env)
  elif args.command=='embed':out=embed_all(args)
  elif args.command=='load-vectors':out=load_vectors(args.db_env)
  elif args.command=='verify':out=verify(args.db_env,allow_pending=True)
  elif args.command=='search':out=search(args)
  elif args.command=='source':out=read_database_source(args)
  else:preflight();stage_text(args.db_env);embed_all(args);out=load_vectors(args.db_env)
  print(json.dumps(out,ensure_ascii=False,indent=2));return 0
 except PilotError as exc:print('ERROR:',str(exc),file=sys.stderr,flush=True);return 2
 except KeyboardInterrupt:print('INTERRUPTED: completed vectors retained; inspect last attempt before retry.',file=sys.stderr);return 130
 except Exception as exc:print('ERROR:',type(exc).__name__+'; details omitted to protect credentials. No completion claimed.',file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
