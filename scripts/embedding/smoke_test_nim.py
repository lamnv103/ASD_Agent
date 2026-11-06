"""One-excerpt NVIDIA NIM embedding pilot; no database, batch indexing or chat calls."""
from __future__ import annotations
import argparse,hashlib,json,math,os,ssl,sys,tempfile,time,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib import request,error

ROOT=Path(__file__).resolve().parents[2]
LIBRARY=ROOT/'knowledge/rag/source_library'
REPORT=ROOT/'reports/embedding_nim_pilot'
MODEL='nvidia/nemotron-3.5-embed-8b'
ENDPOINT='https://integrate.api.nvidia.com/v1/embeddings'
SOURCE_ID='CDC-EARLY-INTERVENTION'
SCOPE='pilot_excerpt_not_complete_document'

class PilotError(Exception):pass

def sha(raw):
 if isinstance(raw,str):raw=raw.encode('utf-8')
 return hashlib.sha256(raw).hexdigest()

def now():
 return datetime.now(timezone(timedelta(hours=7))).isoformat(timespec='seconds')

def atomic_json(path,payload):
 raw=(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode('utf-8')
 path.parent.mkdir(parents=True,exist_ok=True)
 descriptor,name=tempfile.mkstemp(prefix='.'+path.name+'.',suffix='.partial',dir=path.parent)
 try:
  with os.fdopen(descriptor,'wb') as stream:
   stream.write(raw);stream.flush();os.fsync(stream.fileno())
  if Path(name).read_bytes()!=raw:raise PilotError('Temporary result verification failed.')
  os.replace(name,path)
 finally:
  if Path(name).exists():Path(name).unlink()

def pick_sample(body):
 cursor=0
 for block in body.split('\n\n'):
  position=body.find(block,cursor);cursor=position+len(block)
  sample=block.strip()
  if not sample or sample.startswith(('#','[','!','<','>','-','*','|')):continue
  if not 10<=len(sample.split())<=120 or len(sample)>1200:continue
  start=position+len(block)-len(block.lstrip());end=start+len(sample)
  if body[start:end]!=sample:raise PilotError('Sample locator mismatch.')
  return sample,start,end
 raise PilotError('No suitable short original paragraph found; source was not truncated.')

def load_sample():
 path=LIBRARY/'documents.json';raw=path.read_bytes()
 state=json.loads((LIBRARY/'BUILD_STATUS.json').read_text(encoding='utf-8'))
 if state.get('status')!='verified' or not state.get('usable'):raise PilotError('Dataset is not technically verified.')
 if sha(raw)!=state.get('documents_json_sha256'):raise PilotError('Dataset hash differs from published release.')
 entries=[d for d in json.loads(raw)['tai_lieu'] if d['id']==SOURCE_ID]
 if len(entries)!=1:raise PilotError('Expected exactly one accepted CDC source.')
 doc=entries[0];body=doc['noi_dung']
 if sha(body)!=doc['doi_chieu']['sha256_noi_dung']:raise PilotError('Source body hash mismatch.')
 sample,start,end=pick_sample(body)
 return dict(source_id=SOURCE_ID,source_title=doc['ten_tai_lieu'],source_url=doc['nguon']['link_nguon'],
  dataset_file=path.relative_to(ROOT).as_posix(),dataset_sha256=sha(raw),content_sha256=sha(body),
  sample_text=sample,sample_sha256=sha(sample),sample_start_char=start,sample_end_char_exclusive=end,scope=SCOPE)

def request_payload(sample):
 return dict(model=MODEL,input=[sample],input_type='passage',encoding_format='float',truncate='NONE')

def request_fingerprint(meta):
 return sha(json.dumps(dict(request=request_payload(meta['sample_text']),provenance=meta),ensure_ascii=False,sort_keys=True,separators=(',',':')))

def validate_vector(vector):
 if not isinstance(vector,list) or not vector:raise PilotError('Missing or empty embedding vector.')
 if any(type(v) not in (int,float) or not math.isfinite(v) for v in vector):raise PilotError('Embedding has a nonnumeric or nonfinite value.')
 norm=math.hypot(*vector)
 if not math.isfinite(norm) or norm<=0:raise PilotError('Embedding norm is invalid.')
 return norm

def parse_response(payload):
 data=payload.get('data')
 if not isinstance(data,list) or len(data)!=1 or not isinstance(data[0],dict) or data[0].get('index')!=0:raise PilotError('Expected exactly one embedding with index 0.')
 vector=data[0].get('embedding');norm=validate_vector(vector)
 returned=payload.get('model')
 if returned and returned!=MODEL:raise PilotError('Returned model differs from requested embedding model.')
 return vector,norm,returned,payload.get('usage')

def read_key(env_file,key_name):
 if env_file:
  path=Path(env_file).expanduser()
  if not path.is_file():raise PilotError('The supplied .env file does not exist.')
  found=[]
  for raw in path.read_text(encoding='utf-8-sig').splitlines():
   line=raw.strip()
   if not line or line.startswith('#'):continue
   if line.startswith('export '):line=line[7:].lstrip()
   name,sep,value=line.partition('=')
   if not sep or name.strip()!=key_name:continue
   value=value.strip()
   if value.startswith(("'",'"')):
    quote=value[0];close=value.find(quote,1)
    if close<0:raise PilotError('Unclosed quote in the selected .env variable.')
    if value[close+1:].strip() and not value[close+1:].lstrip().startswith('#'):raise PilotError('Unsupported trailing text in the selected .env variable.')
    value=value[1:close]
   else:value=value.split(' #',1)[0].strip()
   found.append(value)
  if not found:
   try:
    import yaml
   except ImportError:raise PilotError('This credential file uses YAML, not dotenv. Install PyYAML in this interpreter or use NVIDIA_API_KEY in the environment.') from None
   try:data=yaml.safe_load(path.read_text(encoding='utf-8-sig'))
   except Exception:raise PilotError('Credential YAML could not be parsed; file contents were not logged.') from None
   if isinstance(data,dict):
    if isinstance(data.get(key_name),str):found.append(data[key_name])
    for model in data.get('models',[]) or []:
     if not isinstance(model,dict) or model.get('model')!=MODEL:continue
     base=model.get('apiBase','https://integrate.api.nvidia.com/v1')
     if model.get('provider') not in {'nvidia','openai'} or not isinstance(base,str) or base.rstrip('/')!='https://integrate.api.nvidia.com/v1':continue
     credential=model.get('apiKey')
     if isinstance(credential,str):found.append(credential)
  if len(found)!=1:raise PilotError('Expected exactly one matching NVIDIA credential. YAML model must equal the selected embedding model; no other credential was used.')
  key=found[0]
 else:key=os.environ.get(key_name,'').strip()
 if not key:raise PilotError('Missing '+key_name+'. Supply --env-file PATH or set the environment variable; do not paste the key into chat.')
 if any(c.isspace() for c in key) or (chr(36)+'{') in key:raise PilotError('Selected credential is not a resolved API key.')
 return key

class NoRedirect(request.HTTPRedirectHandler):
 def redirect_request(self,req,fp,code,msg,headers,newurl):return None

def call_nim(sample,key,timeout):
 context=ssl.create_default_context()
 try:
  import certifi
 except ImportError:pass
 else:context.load_verify_locations(cafile=certifi.where())
 client=request.build_opener(NoRedirect(),request.HTTPSHandler(context=context))
 body=json.dumps(request_payload(sample),ensure_ascii=False).encode('utf-8')
 req=request.Request(ENDPOINT,data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json'},method='POST')
 try:
  with client.open(req,timeout=timeout) as response:
   if response.status!=200:raise PilotError('Unexpected HTTP status '+str(response.status)+'.')
   raw=response.read(4*1024*1024+1)
 except error.HTTPError as exc:
  hints={400:'Check request parameters.',401:'Check NVIDIA credential validity.',403:'Check model access.',404:'Check hosted model availability.',410:'The endpoint/model may have been retired.',429:'Rate limited; no automatic retry was made.'}
  raise PilotError('NVIDIA HTTP '+str(exc.code)+'. '+hints.get(exc.code,'No automatic retry was made.')) from None
 except (TimeoutError,error.URLError,OSError):
  raise PilotError('Network/TLS error or request timeout. Server completion may be unknown; no automatic retry was made.') from None
 if len(raw)>4*1024*1024:raise PilotError('Response exceeds pilot size limit.')
 try:return json.loads(raw)
 except (ValueError,UnicodeError):raise PilotError('API did not return valid JSON.') from None

def check_cached(payload,meta):
 if payload.get('status')!='success' or payload.get('request_fingerprint')!=request_fingerprint(meta):raise PilotError('Existing result does not match this pilot. Preserve it and choose another --output filename.')
 for key,value in meta.items():
  if payload.get(key)!=value:raise PilotError('Cached source provenance mismatch.')
 if payload.get('model_requested')!=MODEL or payload.get('endpoint')!=ENDPOINT or payload.get('input_type')!='passage' or payload.get('encoding_format')!='float' or payload.get('truncate')!='NONE' or payload.get('model_returned') not in (None,MODEL):raise PilotError('Cached model/request settings mismatch.')
 norm=validate_vector(payload.get('embedding'))
 if payload.get('dimensions')!=len(payload['embedding']) or not math.isclose(norm,payload.get('vector_norm',-1),rel_tol=1e-12):raise PilotError('Cached dimensions or norm mismatch.')
 return payload

def display(payload,path,full,cached):
 print('STATUS: success; '+('cached result, no API call' if cached else 'real NVIDIA API response'),flush=True)
 print('SOURCE:',payload['source_id'],'-',payload['source_title'])
 print('SOURCE_URL:',payload['source_url'])
 print('SAMPLE:',payload['sample_text'])
 print('MODEL:',payload['model_requested'])
 print('DIMENSIONS:',payload['dimensions'])
 print('VECTOR_NORM:',payload['vector_norm'])
 print('USAGE:',json.dumps(payload.get('usage'),ensure_ascii=False))
 print('ELAPSED_SECONDS:',payload['elapsed_seconds'])
 print('VECTOR_FULL:' if full else 'VECTOR_PREVIEW_FIRST_16:',json.dumps(payload['embedding'] if full else payload['embedding'][:16]))
 print('RESULT:',str(path))
 print('SCOPE: one original excerpt only; no whole-document embedding or database changes.',flush=True)

def run(args):
 meta=load_sample()
 if not 1<=args.timeout<=60:raise PilotError('--timeout must be between 1 and 60 seconds.')
 output=Path(args.output).resolve() if args.output else REPORT/'pilot_embedding.json'
 if not output.resolve().is_relative_to(REPORT.resolve()):raise PilotError('Pilot output must stay inside reports/embedding_nim_pilot.')
 if output.exists():
  payload=check_cached(json.loads(output.read_text(encoding='utf-8')),meta)
  display(payload,output,args.print_full,True);return
 print('PILOT: one excerpt;',len(meta['sample_text']),'characters;',len(meta['sample_text'].split()),'whitespace-separated words (not a token count).',flush=True)
 print('MODEL:',MODEL,flush=True)
 if args.dry_run:
  print('DRY_RUN_SAMPLE:',meta['sample_text']);print('NO API CALL; no embedding file created.');return
 key=read_key(args.env_file,args.key_name)
 REPORT.mkdir(parents=True,exist_ok=True)
 lock=REPORT/'request.lock'
 attempt=REPORT/('attempt-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]+'.json')
 attempt_row=dict(status='started',started_at=now(),request_fingerprint=request_fingerprint(meta),source_id=meta['source_id'],model=MODEL,endpoint=ENDPOINT,output=str(output.relative_to(ROOT)),automatic_retries=0)
 try:
  with lock.open('x',encoding='utf-8') as stream:json.dump(dict(pid=os.getpid(),started_at=now(),attempt=attempt.name),stream)
 except FileExistsError:raise PilotError('A pilot request lock exists. Check its process before retrying; no API call made.') from None
 try:
  atomic_json(attempt,attempt_row)
  print('Calling NVIDIA /embeddings; timeout',args.timeout,'seconds; no automatic retries.',flush=True)
  started=time.monotonic();response=call_nim(meta['sample_text'],key,args.timeout)
  elapsed=round(time.monotonic()-started,6)
  vector,norm,returned,usage=parse_response(response)
  payload=dict(status='success',provider='NVIDIA NIM',model_requested=MODEL,model_returned=returned,endpoint=ENDPOINT,created_at=now(),
   input_type='passage',encoding_format='float',truncate='NONE',**meta,request_fingerprint=request_fingerprint(meta),
   dimensions=len(vector),embedding=vector,vector_norm=norm,usage=usage,elapsed_seconds=elapsed)
  check_cached(payload,meta);atomic_json(output,payload);check_cached(json.loads(output.read_text(encoding='utf-8')),meta)
  attempt_row.update(status='success',finished_at=now(),result_sha256=sha(output.read_bytes()),dimensions=len(vector),elapsed_seconds=elapsed)
  atomic_json(attempt,attempt_row);display(payload,output,args.print_full,False)
 except BaseException as exc:
  attempt_row.update(status='not_completed_locally',finished_at=now(),error_type=type(exc).__name__,remote_completion='unknown; inspect before another paid request')
  atomic_json(attempt,attempt_row);raise
 finally:lock.unlink(missing_ok=True)

def main(argv=None):
 global MODEL
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--model',choices=['nvidia/nemotron-3.5-embed-8b','nvidia/nemotron-3-embed-1b'],default=MODEL)
 parser.add_argument('--dry-run',action='store_true')
 parser.add_argument('--print-full',action='store_true')
 parser.add_argument('--timeout',type=int,default=45)
 parser.add_argument('--env-file',help='Read only the selected key from this .env; never copy/log credentials.')
 parser.add_argument('--key-name',default='NVIDIA_API_KEY')
 parser.add_argument('--output',help='Optional result filename inside the pilot report directory.')
 args=parser.parse_args(argv);MODEL=args.model
 try:run(args)
 except PilotError as exc:print('ERROR:',str(exc),file=sys.stderr,flush=True);return 2
 except KeyboardInterrupt:print('INTERRUPTED: no success was claimed; check attempt status before retry.',file=sys.stderr);return 130
 except Exception as exc:
  print('ERROR:',type(exc).__name__+'; no success claimed. Raw exception omitted to protect credentials.',file=sys.stderr);return 2
 return 0

if __name__=='__main__':raise SystemExit(main())
